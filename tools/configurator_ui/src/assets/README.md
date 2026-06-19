# Image Assets

Add your images to this folder and import them in `QuestionStep.jsx`.

## All Required Images

Place these image files in `src/assets/`:

**Indoor/Outdoor:**
- `indoor-outdoor-indoor.jpg`
- `indoor-outdoor-outdoor.jpg`

**Moisture:**
- `moisture-dry.jpg`
- `moisture-damp.jpg`
- `moisture-wet.jpg`

**IP Rating:**
- `ip-rating-ip65.jpg`
- `ip-rating-ip67.jpg`
- `ip-rating-ip68.jpg`

**Color Mode:**
- `color-mode-analog-rgb.jpg`
- `color-mode-addressable-pixel.jpg`

**Fixture Purpose:**
- `fixture-purpose-accent.jpg`
- `fixture-purpose-task.jpg`
- `fixture-purpose-ambient.jpg`

**Installation Method:**
- `installation-method-surface.jpg`
- `installation-method-recessed.jpg`
- `installation-method-angled.jpg`
- `installation-method-drywall-plaster-in.jpg`
- `installation-method-suspended.jpg`

**Target CCT:**
- `target-cct-2700k.jpg`
- `target-cct-3000k.jpg`
- `target-cct-3500k.jpg`
- `target-cct-4000k.jpg`

**CRI:**
- `cri-90-plus.jpg`
- `cri-95-plus.jpg`

**Continuous Run:**
- `continuous-run-yes.jpg`
- `continuous-run-no.jpg`

**Supply Voltage:**
- `supply-voltage-24vdc.jpg`
- `supply-voltage-120vac.jpg`

**Dimming Protocol:**
- `dimming-protocol-0-10v.jpg`
- `dimming-protocol-triac.jpg`
- `dimming-protocol-elv.jpg`
- `dimming-protocol-dali.jpg`
- `dimming-protocol-dmx512.jpg`
- `dimming-protocol-spi.jpg`

**Diffuser:**
- `diffuser-clear.jpg`
- `diffuser-frosted.jpg`
- `diffuser-white.jpg`
- `diffuser-black.jpg`

**Finish:**
- `finish-silver.jpg`
- `finish-black.jpg`
- `finish-white.jpg`

## Setup Steps

1. **Add all your images** from the list above to this `src/assets/` folder

2. **Import them** in `src/components/QuestionStep.jsx` at the top:
   ```javascript
   import indoorImg from '../assets/indoor-outdoor-indoor.jpg';
   import outdoorImg from '../assets/indoor-outdoor-outdoor.jpg';
   import dryImg from '../assets/moisture-dry.jpg';
   import dampImg from '../assets/moisture-damp.jpg';
   // ... continue for all 42 images
   ```

3. **Add to imageMap** in `QuestionStep.jsx`:
   ```javascript
   const imageMap = {
     'indoor-outdoor-indoor': indoorImg,
     'indoor-outdoor-outdoor': outdoorImg,
     'moisture-dry': dryImg,
     'moisture-damp': dampImg,
     // ... continue mapping all 42 imageIds to their imports
   };
   ```

## Fallback Colors

All options have color fallbacks defined in `questions.json`. If an image is missing from the map, the color will display instead:
- Warm tones for warmth-related options (CCT, light type)
- Cool/blue tones for water/damp ratings
- Neutral/gray tones for neutral options
- Gradient colors for full-color/RGB options

## Format

- Supported: `.jpg`, `.png`, `.webp`, `.svg`
- Recommended: `.jpg` for photos, `.png` for graphics
- Size: 200-400px wide (responsive, will scale automatically)
- Total: 42 images to add
