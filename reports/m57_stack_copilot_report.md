# ATHENA Copilot report — stack.fits

## Measured metrics
| Metric | Value |
|---|---|
| empty_pixel_fraction | 0 |
| low_coverage_border_px (left,right,top,bottom) | 59,0,66,8 |
| low_coverage_fraction | 0.1176 |
| background_median | 3887 |
| noise_robust_sigma | 48.5 |
| measured_region (x0:x1, y0:y1) | 85:1278, 85:949 |
| column_banding_index | 0.06374 |
| row_banding_index | 0.03827 |
| corner_medians | [3899.8676, 3909.7134, 3847.7769, 3811.2324] |
| gradient_index | 2.03 |
| clipped_fraction | 7.857e-07 |
| shape | 1304x976 |

## Provenance
```
DATE = 2026-06-18T05:20:29.396
EXPTIME = 3.971754
NCOMBINE = 155
INSTRUME = IMX224
GAIN = 0.1287112
```

## Copilot assessment (AI-generated, hypotheses)
## What I see
* **Prominent uncropped stacking borders:** A dark, low-coverage border is clearly visible along the top and left edges (visual impression), corresponding to measured `low_coverage_border_px` of 59 px (left) and 66 px (top), accounting for ~11.8% of the frame (`low_coverage_fraction: 0.1176`).
* **High background pedestal and light-pollution/vignetting tilt:** The image displays a bright, washed-out sky floor (`background_median: 3887`, `noise_robust_sigma: 48.5`) with measurable corner-to-corner drift (`corner_medians` spanning ~3811 to ~3910, `gradient_index: 2.03`).
* **Small planetary nebula centered in field:** M57 (the Ring Nebula) is visible near the center surrounded by a modest star field with negligible clipping (`clipped_fraction: 7.857e-07`).
* **Measurable residual column/row pattern:** Despite per-frame destriping, residual directionality remains in the readout (`column_banding_index: 0.06374`, `row_banding_index: 0.03827`).

## Likely causes
* **Hypothesis (Stacking Border Artifacts):** Field rotation and alt-az dither during the 155 sub-exposures created low-coverage stacking margins (top and left) that will severely corrupt background modeling if not removed first.
* **Hypothesis (Sensor Temperature Drift):** Operating at an elevated sensor temperature of 33 °C can cause the fixed-pattern noise profile to drift away from the matched master dark, leaving residual banding that survives per-frame destriping.
* **Hypothesis (Uncorrected Gradients / Vignetting):** As typical for eVscope workflows without flat frames, optical falloff and skyglow produce smooth illumination variations across the frame (`gradient_index: 2.03`).

## Recommended next step in ATHENA
**Step 6: Crop**
* **Action:** Crop out the low-coverage registration borders before proceeding to background extraction (crop at least 66 px from the top, 59 px from the left, and 8 px from the bottom). 
* **Starting parameter:** Set crop margins to slightly exceed measured borders: Left: 65 px, Right: 5 px, Top: 72 px, Bottom: 12 px (or use the measured region bounding box `85:1278, 85:949`).
* **How to check:** `low_coverage_fraction` and `empty_pixel_fraction` should both drop to `0.0`. This prevents GraXpert AI (Step 7) from treating the dark borders as sky floor and blooming artificial light across the frame.

## Do not
* **Do not run GraXpert denoise (Step 10) to remove the residual banding:** Denoisers cannot resolve coherent fixed-pattern lines and will smudge real background structure while leaving banding visible.
* **Do not apply GraXpert background extraction (Step 7) before cropping:** Feeding the dark low-coverage borders into the background model will cause severe regional over-subtraction and background bloat.
