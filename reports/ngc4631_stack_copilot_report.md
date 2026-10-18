# ATHENA Copilot report — stack.fits

## Measured metrics
| Metric | Value |
|---|---|
| empty_pixel_fraction | 0 |
| low_coverage_border_px (left,right,top,bottom) | 0,0,0,0 |
| low_coverage_fraction | 0 |
| background_median | 2790 |
| noise_robust_sigma | 126.3 |
| measured_region (x0:x1, y0:y1) | 26:1278, 19:957 |
| column_banding_index | 0.09733 |
| row_banding_index | 0.1024 |
| corner_medians | [3186.4735, 2826.3672, 3094.5231, 2677.0051] |
| gradient_index | 4.035 |
| clipped_fraction | 7.857e-07 |
| shape | 1304x976 |
| data_state | linear (sensor ADU) - early in the chain |

## Provenance
```
DATE = 2026-05-02T09:24:15.988
EXPTIME = 3.971754
NCOMBINE = 30
INSTRUME = IMX224
GAIN = 0.1287112
```

## Copilot assessment (AI-generated, hypotheses)
## What I see
* Linear raw stack showing an edge-on/inclined spiral galaxy in the center, heavily dominated by sky background and read noise (`data_state: linear (sensor ADU)`).
* Strong, uneven background illumination with a prominent bright ramp on the left edge (`gradient_index: 4.035`, `corner_medians` ranging from ~2677 ADU bottom-right to ~3186 ADU top-left).
* Pervasive magenta/purple color cast across the frame (visual impression), typical of uncalibrated Bayer data prior to color correction.
* Significant high-frequency noise floor (`noise_robust_sigma: 126.3`) from a modest total exposure time (~2 minutes across `NCOMBINE = 30` frames).

## Likely causes
* **Hypothesis: Uncorrected sensor vignetting and light pollution/sky glow.** Without flat frames on the eVscope system, field gradients and corner falloff remain uncorrected, producing the high `gradient_index` (4.035) and prominent edge glow.
* **Hypothesis: Raw sensor color balance.** The image is still linear and uncalibrated; the IMX224 Bayer matrix response creates a strong background tint before neutralisation.

## Recommended next step in ATHENA
* **Step 7: GraXpert AI background extraction.**  
  Run background extraction to remove the severe 4.035 gradient and level the field before colour balancing and stretching.  
  *How to check:* The `gradient_index` should drop significantly (approaching < 1.5–2.0), and the bright illumination gradient across the left edge should flatten out to a uniform level.

## Do not
* **Do not apply histogram stretching (Step 9) or saturation (Step 11) yet.** Stretching this data while the 4.035 gradient is present will severely clip the right side while blowing out the bright left border into a solid wash.
* **Do not apply GraXpert denoise (Step 10) in an attempt to clean up the background grain at this stage;** denoising belongs late in the chain after background extraction and stretching.
