# Convert PDFs to a reviewable Markdown form before building cards

Extraction and card-building are two separately runnable stages: a lesson goes from PDF to Markdown, and only then from Markdown to a card.

Parsing a PDF straight into cards would have fewer moving parts, which is why it is the default shape for a tool like this. It is rejected because roughly seventy lessons exist only as image-only scans whose text comes from OCR, and an OCR error baked directly into a card has nowhere to be reviewed or corrected. The Markdown is a seam that three sources converge on — text-layer PDFs, scanned PDFs, and the print transcript — so an error can be fixed once, in a file a human can read, instead of in every note that inherited it. It also turns the print-transcript cross-check into a diff between two Markdown files rather than a PDF-to-PDF comparison.

The cost is an intermediate artifact to keep in step with its source, and a rule about which wins when they disagree.
