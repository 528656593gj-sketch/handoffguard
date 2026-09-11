# Demo case: video delivery audit and repair

This case uses anonymized, user-owned test files. No workplace data or internal rules are included.

## Delivery requirement

- One final MP4 video.
- One SRT subtitle file.
- Three JPG or PNG cover images.
- One project description document.
- No duplicates, temporary files, or ambiguous final versions.

## Initial package findings

- Two byte-identical final videos.
- Two byte-identical images.
- A final video with the repeated extension `.mp4.mp4`.
- A PNG image named with a `.jpg` extension.
- Subtitle text saved by Word as `captions.srt.docx`.
- A Word document named with a `.txt` extension.
- macOS metadata and `.DS_Store` files.

## Safe repair

The original ZIP was preserved. HandoffGuard created a new archive that:

- removed byte-identical duplicates and package metadata;
- normalized the final video filename;
- corrected image and Office document extensions using file signatures;
- extracted valid subtitle text from the Word document into UTF-8 SRT.

## Final result

```text
Status: PASS
Files: 6
Errors: 0
Warnings: 0
```

The final package contained one MP4, one SRT, three unique PNG covers, and one DOCX project description.
