# ATHENA Copilot report — processed.fits

## Measured metrics
| Metric | Value |
|---|---|
| empty_pixel_fraction | 0 |
| low_coverage_border_px (left,right,top,bottom) | 4,0,0,0 |
| low_coverage_fraction | 0.003067 |
| background_median | 0.2532 |
| noise_robust_sigma | 0.002684 |
| measured_region (x0:x1, y0:y1) | 30:1278, 19:957 |
| column_banding_index | 0.1543 |
| row_banding_index | 0.09899 |
| corner_medians | [0.2826, 0.2539, 0.2837, 0.2529] |
| gradient_index | 11.49 |
| clipped_fraction | 7.857e-07 |
| shape | 1304x976 |
| data_state | normalised 0-1 - likely already processed/stretched |

## Provenance
```
Header present, but no provenance keywords.
```

## Copilot assessment (AI-generated, hypotheses)
## What I see
- Severe edge glow / light leak along the left border and top-left corner (visual impression), consistent with the elevated top-left and bottom-left corner medians (`0.2826`, `0.2837` vs ~`0.253` on the right) and a high `gradient_index` of `11.49`.
- Heavy, multicoloured chrominance speckle and mottled noise across the background sky (visual impression), even though `noise_robust_sigma` is relatively low at `0.002684` due to stretching.
- High residual background pedestal (`background_median: 0.2532`), leaving the background gray rather than neutral dark sky.
- An edge-on spiral galaxy visible near the center with a prominent dark absorption ring or artifact around its nucleus (visual impression).

## Likely causes
- **Hypothesis: Flare or uncorrected edge artifact left in during background extraction.** The bright flare along the left edge was likely treated as sky by background extraction or improperly modeled, corrupting the gradient model across the entire frame.
- **Hypothesis: Color saturation applied without adequate background protection.** Boosting saturation without sufficient background protection (~0.4) amplifies background color noise into intense red, green, and blue grain (chrominance speckle).
- **Hypothesis: Over-subtraction around the galaxy core.** The dark hollow surrounding the galaxy's center suggests local background over-subtraction or an over-aggressive ringing artifact from processing/filtering.

## Recommended next step in ATHENA
Redo **Step 6 (crop)**, followed by re-running Step 7 (GraXpert AI background extraction). Aggressively crop the left and upper borders to completely eliminate the bright edge glow before extracting the background. You can confirm this worked if `gradient_index` drops substantially below `11.49` and the `corner_medians` become uniform across all four corners.

## Do not
- Do not apply additional saturation (Step 11) or denoise (Step 10) to fix the noisy background; denoisers cannot fix severe background gradient artifacts, and saturation without background protection will only worsen the colorful background speckle.
- Do not stretch the image any further, as stretching an uncorrected gradient will completely blow out the left margin and wash out the galaxy.
