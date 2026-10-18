"""
ATHENA Copilot — a companion tool for ATHENA (github.com/cassaiub/athena).

Upload a stacked FITS (or a PNG/JPG preview). The app:
  1. MEASURES simple, reproducible quality numbers with numpy (no AI),
  2. reads ATHENA provenance (CREATOR / CALSTAT / HISTORY) from the FITS header,
  3. sends a stretched preview + the numbers + ATHENA's processing notes to Gemini,
     which explains the numbers and suggests the next step in the ATHENA chain.

The AI explains; the numbers are computed. Raw data never leaves the machine —
only a small 8-bit preview JPEG is sent to the API.

Run:
  pip install streamlit requests numpy astropy pillow
  set GEMINI_API_KEY=...        (Windows cmd)   or paste it in the sidebar
  streamlit run app.py
"""
import base64
import hashlib
import io
import os

import numpy as np
import requests
import streamlit as st
from PIL import Image

try:
    from astropy.io import fits
except ImportError:  # app still works for PNG/JPG
    fits = None

# ---------------------------------------------------------------- knowledge
# Grounding for the model: ATHENA's real chain and lessons learned on real data.
ATHENA_NOTES = """
ATHENA processing chain (in order):
1 matched master dark, 2 per-frame destripe, 3 debayer, 4 global star alignment,
5 winsorized sigma rejection (5.0 sigma), 6 crop, 7 GraXpert AI background extraction,
8 manual colour calibration (background neutralise, then grey-world),
9 histogram stretch (midtones ~0.10 nebulae, ~0.20 globular clusters),
10 GraXpert denoise (~0.30), 11 saturation (~0.2) with background protection (~0.4).

Lessons from real Unistellar eVscope (IMX224) data:
- Crop BEFORE background modelling: low-coverage registration borders are treated as sky
  and bloom the background model across the frame.
- Globular clusters need a gentler stretch than nebulae; the core saturates otherwise.
- Background protection on saturation stops background grain turning into colour speckle.
- Denoisers (GraXpert, NLM, wavelet) cannot remove fixed-pattern banding; destripe can.
- Fixed-pattern noise does not average out with stacking; deeper stacks make it MORE visible.
- Destripe per frame, not on the master (registration rotates each frame's banding).
- Residual banding can come from temperature drift of the fixed pattern (unconfirmed).
- Without flats, vignetting is uncorrected; manual colour is visual, not photometric.
- No plate-solving / photometric colour calibration on machines without astrometry.
"""

PROMPT = """You are ATHENA Copilot, an assistant for astrophotographers using the ATHENA
open-source processing tool. You are given: a stretched preview of a stacked image,
MEASURED quality metrics (computed in numpy, trustworthy), provenance from the FITS
header, the ATHENA notes below, and the user's note.

{notes}

MEASURED METRICS:
{metrics}

PROVENANCE (FITS header):
{prov}

USER NOTE: {user_note}

If data_state says "already processed": do NOT recommend steps that normally come before
background extraction (crop, GraXpert) as if they were never run. Instead judge the RESULT:
what the earlier steps left behind, and say which step to redo and why. Note that on
stretched/denoised data the noise is much lower, so ratio indices read higher than on
the linear stack and are not directly comparable.

Respond in Markdown with exactly these sections:
## What I see
3-5 bullets. Tie each observation to a metric where possible. Clearly mark anything
you only infer from the preview as "(visual impression)".
## Likely causes
Bullets, each labelled as a hypothesis. Use the ATHENA lessons; do not invent features.
## Recommended next step in ATHENA
ONE step from the ATHENA chain (name it by its number), with a starting parameter if
the notes give one, and how to check it worked (which metric should move, and which way).
## Do not
1-2 things that would make it worse (e.g. denoising banding, stretching harder).
Never claim photometric accuracy. Never invent star counts or object facts not visible."""


# ---------------------------------------------------------------- loading
def load_image(uploaded):
    """Return (float32 2D luminance array, header-or-None, colour preview array)."""
    name = uploaded.name.lower()
    raw = uploaded.getvalue()
    if name.endswith((".fits", ".fit", ".fts")):
        if fits is None:
            st.error("astropy not installed: pip install astropy")
            st.stop()
        with fits.open(io.BytesIO(raw)) as hdul:
            hdu = next(h for h in hdul if h.data is not None)
            data = np.asarray(hdu.data, dtype=np.float32)
            header = hdu.header
        # Colour cubes may be (3,H,W) or (H,W,3)
        if data.ndim == 3:
            if data.shape[0] in (3, 4):
                data = np.moveaxis(data[:3], 0, -1)
            colour = data[..., :3]
            lum = colour.mean(axis=-1)
        else:
            colour, lum = None, data
        return lum, header, colour
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    colour = np.asarray(img, dtype=np.float32)
    return colour.mean(axis=-1), None, colour


def stretch(arr):
    """Asinh auto-stretch to 8-bit for preview only."""
    a = np.nan_to_num(arr.astype(np.float32))
    lo, hi = np.percentile(a, 0.5), np.percentile(a, 99.8)
    a = np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)
    a = np.arcsinh(10 * a) / np.arcsinh(10)
    return (a * 255).astype(np.uint8)


def preview_jpeg(lum, colour, max_side=1024):
    arr = stretch(colour) if colour is not None else stretch(lum)
    img = Image.fromarray(arr)
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue(), img


# ---------------------------------------------------------------- metrics
def robust_sigma(x):
    x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if x.size else float("nan")


def smooth_1d(v, k):
    k = max(3, int(k) | 1)
    pad = np.pad(v, k // 2, mode="edge")
    return np.convolve(pad, np.ones(k) / k, mode="valid")


def compute_metrics(lum):
    """Simple, reproducible metrics. These are THIS tool's definitions,
    not ATHENA's internal col_ratio/row_ratio."""
    a = np.nan_to_num(lum.astype(np.float64))
    h, w = a.shape
    m = {}

    # Work on an inner crop so borders don't dominate
    ch, cw = int(h * 0.05), int(w * 0.05)
    inner = a[ch:h - ch, cw:w - cw]
    noise = robust_sigma(inner)
    bg = float(np.median(inner))

    # Border coverage: edge rows/cols that are empty OR much dimmer than the sky
    # (low-coverage registration borders are dim, not always exactly 0).
    zero = (a == 0) | ~np.isfinite(lum)
    m["empty_pixel_fraction"] = float(zero.mean())
    thresh = bg - 5 * noise
    col_med, row_med = np.median(a, axis=0), np.median(a, axis=1)

    def edge_run(v):
        left = 0
        while left < len(v) and v[left] < thresh:
            left += 1
        right = 0
        while right < len(v) - left and v[len(v) - 1 - right] < thresh:
            right += 1
        return left, right

    l, r = edge_run(col_med)
    t, b = edge_run(row_med)
    m["low_coverage_border_px (left,right,top,bottom)"] = f"{l},{r},{t},{b}"
    covered = (w - l - r) * (h - t - b)
    m["low_coverage_fraction"] = float(1 - covered / (w * h)) if w * h else 0.0

    # Re-measure INSIDE the detected border (+2% safety margin) so dim border
    # rows/cols don't masquerade as banding or gradient.
    mh, mw = int(h * 0.02), int(w * 0.02)
    y0, y1 = t + mh, h - b - mh
    x0, x1 = l + mw, w - r - mw
    if y1 - y0 > 32 and x1 - x0 > 32:
        inner = a[y0:y1, x0:x1]
        noise = robust_sigma(inner)
        bg = float(np.median(inner))
        m["background_median"] = bg
        m["noise_robust_sigma"] = float(noise)
    m["measured_region (x0:x1, y0:y1)"] = f"{x0}:{x1}, {y0}:{y1}"
    m["background_median"] = bg
    m["noise_robust_sigma"] = float(noise)

    # Banding index: high-passed spread of column (row) medians relative to pixel noise.
    # Values near ~0.1 or lower = little pattern; much higher = visible banding.
    for axis, key in ((0, "column_banding_index"), (1, "row_banding_index")):
        prof = np.median(inner, axis=axis)
        hp = prof - smooth_1d(prof, len(prof) // 20)
        m[key] = float(np.std(hp) / noise) if noise > 0 else float("nan")

    # Background gradient: spread of corner-patch medians relative to noise
    ph, pw = max(8, inner.shape[0] // 8), max(8, inner.shape[1] // 8)
    corners = [inner[:ph, :pw], inner[:ph, -pw:], inner[-ph:, :pw], inner[-ph:, -pw:]]
    cm = [float(np.median(c)) for c in corners]
    m["corner_medians"] = [round(c, 4) for c in cm]
    m["gradient_index"] = float((max(cm) - min(cm)) / noise) if noise > 0 else float("nan")

    # Saturation / clipping
    top = np.nanmax(a)
    m["clipped_fraction"] = float((a >= 0.999 * top).mean()) if top > 0 else 0.0
    m["shape"] = f"{w}x{h}"
    m["data_state"] = ("linear (sensor ADU) - early in the chain" if np.nanmax(a) > 2.0
                       else "normalised 0-1 - likely already processed/stretched")
    return m


def read_provenance(header):
    if header is None:
        return "No FITS header (PNG/JPG upload)."
    lines = []
    for key in ("CREATOR", "DATE", "CALSTAT", "EXPTIME", "NCOMBINE", "OBJECT",
                "INSTRUME", "CCD-TEMP", "BAYERPAT", "GAIN"):
        if key in header:
            lines.append(f"{key} = {header[key]}")
    hist = [str(h) for h in header.get("HISTORY", [])]
    athena_hist = [h for h in hist if h.startswith("Athena")] or hist
    if athena_hist:
        lines.append("HISTORY:")
        lines += [f"  {h}" for h in athena_hist[:40]]
    return "\n".join(lines) if lines else "Header present, but no provenance keywords."


# ---------------------------------------------------------------- gemini
def ask_gemini(api_key, model, jpeg, metrics, prov, user_note):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key}")
    metric_txt = "\n".join(f"{k}: {v:.4g}" if isinstance(v, float) else f"{k}: {v}"
                           for k, v in metrics.items())
    payload = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": "image/jpeg",
                         "data": base64.b64encode(jpeg).decode()}},
        {"text": PROMPT.format(notes=ATHENA_NOTES, metrics=metric_txt, prov=prov,
                               user_note=user_note or "(none)")},
    ]}],
        # Low thinking keeps answers fast enough for a live demo
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
    try:
        # (connect, read): fail fast if unreachable or the model is too slow
        r = requests.post(url, json=payload, timeout=(10, 90))
        if r.status_code == 400 and "thinking" in r.text.lower():
            # Model doesn't accept thinkingLevel: retry once without it
            del payload["generationConfig"]
            r = requests.post(url, json=payload, timeout=(10, 90))
    except requests.exceptions.ReadTimeout:
        return (f"**Error:** {model} did not answer within 90 s (request timed out). "
                "Try again, or try a different model in the sidebar.")
    except requests.exceptions.RequestException as e:
        # Type name only: str(e) can include the request URL, which carries the API key
        return f"**Error:** could not reach the Gemini API ({type(e).__name__})."
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        return f"**Error {r.status_code}:** {msg}"
    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip() \
        or "Error: empty response."


def build_report(name, metrics, prov, advice):
    mt = "\n".join(f"| {k} | {v:.4g} |" if isinstance(v, float) else f"| {k} | {v} |"
                   for k, v in metrics.items())
    return (f"# ATHENA Copilot report — {name}\n\n## Measured metrics\n"
            f"| Metric | Value |\n|---|---|\n{mt}\n\n## Provenance\n```\n{prov}\n```\n\n"
            f"## Copilot assessment (AI-generated, hypotheses)\n{advice}\n")


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="ATHENA Copilot", page_icon="🔭", layout="wide")
st.title("🔭 ATHENA Copilot")
st.caption("Measured diagnostics + Gemini explanations for ATHENA astrophotography stacks. "
           "Numbers are computed; AI text is labelled as hypotheses.")

with st.sidebar:
    api_key = st.text_input("Gemini API key", type="password",
                            value=os.getenv("GEMINI_API_KEY", ""))
    model = st.text_input("Model", value="gemini-3.8-flash",
                          help="Any model name from AI Studio, e.g. gemini-3.8-flash")
    st.markdown("Only an 8-bit preview JPEG is sent to the API; the FITS stays local.")

uploaded = st.file_uploader("Stacked image (FITS preferred, PNG/JPG ok)",
                            type=["fits", "fit", "fts", "png", "jpg", "jpeg"])
user_note = st.text_input("What are you trying to do? (optional)",
                          placeholder="e.g. M57 stack, residual banding after destripe, 33 °C sensor")

if uploaded:
    file_id = hashlib.md5(uploaded.getvalue()).hexdigest()
    lum, header, colour = load_image(uploaded)
    jpeg, prev = preview_jpeg(lum, colour)
    metrics = compute_metrics(lum)
    prov = read_provenance(header)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.image(prev, caption="Auto-stretched preview (display only)", use_container_width=True)
    with c2:
        st.subheader("Measured")
        k1, k2 = st.columns(2)
        k1.metric("Column banding", f"{metrics['column_banding_index']:.2f}")
        k2.metric("Row banding", f"{metrics['row_banding_index']:.2f}")
        k1.metric("Gradient index", f"{metrics['gradient_index']:.1f}")
        k2.metric("Clipped %", f"{100 * metrics['clipped_fraction']:.2f}")
        st.metric("Low-coverage border %", f"{100 * metrics['low_coverage_fraction']:.2f}",
                  help="Edge rows/cols much dimmer than the sky (L,R,T,B px: "
                       + metrics["low_coverage_border_px (left,right,top,bottom)"] + ")")
        with st.expander("Provenance (FITS header)"):
            st.code(prov)

    if st.button("Ask Copilot", type="primary"):
        if not api_key:
            st.error("Add your Gemini API key in the sidebar.")
            st.stop()
        with st.spinner(f"Asking {model}..."):
            st.session_state.advice = ask_gemini(api_key, model, jpeg, metrics, prov, user_note)
            st.session_state.advice_for = file_id

    if st.session_state.get("advice_for") == file_id:
        st.markdown(st.session_state.advice)
        st.download_button("Download processing report (.md)",
                           build_report(uploaded.name, metrics, prov, st.session_state.advice),
                           file_name=f"{uploaded.name}_{file_id[:6]}_copilot_report.md")
