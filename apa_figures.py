"""APA 7-style export wrapper for locally generated statistical figures.

The original plot pixels remain unchanged and are not re-analysed. APA 7
requires figure number, italic title, legible axes and figure notes; users
must still check journal-specific image resolution, captions and ordering.
"""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from output_workspace import PNG_SIGNATURE


DEFAULT_NOTE = (
    "Note. Generated from the current analysis. Interpret plotted estimates "
    "with their numerical report, sample size and assumptions. "
    "Renumber the figure to match its order in the manuscript."
)


# Current plotting functions usually include fixed legacy figure numbers (1–14).
# Descriptive graphs are the only exception; they have no embedded Figure header.
EMBEDDED_CAPTION_SECTIONS = frozenset({
    "reliability", "omega", "factor", "correlation", "matrix",
    "groups", "paired", "chi", "omnibus", "regression", "logistic",
    "ancova", "repeated",
})

SECTION_NOTES = {
    "descriptive": "Note. Frequencies and distributions are descriptive; "
                   "confirm the measurement scale and treatment of missing values.",
    "reliability": "Note. Error bars apply only to the full-scale Cronbach alpha. "
                   "Item-deletion estimates have no displayed confidence intervals. "
                   "Reliability does not establish construct validity.",
    "omega": "Note. One-factor omega uses a Pearson-based factor model; "
             "loadings and correlations depend on assumptions and complete cases.",
    "factor": "Note. EFA estimates common-factor structure, while PCA reduces "
              "total variance. Retention and rotation decisions remain exploratory.",
    "correlation": "Note. The plotted relationship is not evidence of causality. "
                   "Tied Spearman scores may be jittered for display only; "
                   "estimates use the original observations.",
    "matrix": "Note. Correlations are exploratory associations, not causation. "
              "Different pairs may have different effective sample sizes.",
    "groups": "Note. Compare distributions and assumptions before interpreting "
              "between-group differences as effects.",
    "paired": "Note. Connected observations belong to the same participants. "
              "Within-person changes alone do not establish causation.",
    "chi": "Note. Sparse expected counts can invalidate asymptotic chi-square "
           "approximations; check the numerical report.",
    "omnibus": "Note. Group comparisons depend on design, distributional "
               "assumptions and multiple-test correction; no causation implied.",
    "regression": "Note. Fitted associations and residual diagnostics are "
                  "in-sample; they do not establish causality or external accuracy.",
    "logistic": "Note. ROC and calibration are in-sample diagnostics, not "
                "external validation or a causal claim.",
    "ancova": "Note. Adjusted means depend on covariate reference values "
              "and the common-slope or interaction model.",
    "repeated": "Note. Trajectories describe repeated measurements within "
                "participants; check sphericity, missingness and design.",
}


def default_section_figure_note(section: str) -> str:
    return SECTION_NOTES.get(section, DEFAULT_NOTE)


def section_embeds_figure_header(section: str) -> bool:
    return section in EMBEDDED_CAPTION_SECTIONS


def make_apa7_export_png(
    original_png: bytes, title: str, *,
    figure_number: int = 1, note: str = DEFAULT_NOTE,
    dpi: int = 300, strip_embedded_caption: bool = False,
) -> bytes:
    """Add manuscript-style number, italic title and explanatory note.

    This is an export layout, not a guarantee that the source chart's pixel
    density or every research-specific caption meets a publisher requirement.
    """
    if not isinstance(original_png, bytes) or not original_png.startswith(PNG_SIGNATURE):
        raise ValueError("A valid PNG chart is required.")
    if len(original_png) > 25_000_000:
        raise ValueError("PNG chart is too large for safe figure export.")
    if isinstance(figure_number, bool) or not isinstance(figure_number, int):
        raise ValueError("Figure number must be a positive whole number.")
    if not 1 <= figure_number <= 999:
        raise ValueError("Figure number must be between 1 and 999.")
    if dpi < 150 or dpi > 600:
        raise ValueError("Figure resolution must be between 150 and 600 dpi.")
    if not isinstance(title, str) or not title.strip() or len(title) > 220:
        raise ValueError("Figure title must be 1–220 characters.")
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError("Figure note must be no more than 500 characters.")
    with Image.open(BytesIO(original_png)) as photo:
        if photo.width * photo.height > 24_000_000:
            raise ValueError("PNG chart has too many pixels.")
        source_image = photo.convert("RGBA").copy()
    if strip_embedded_caption:
        # Older plots in this project embed hard-coded Figure numbers in the
        # top margin and their Note in the bottom margin. Their matplotlib
        # layouts reserve roughly 10–15% top and 8–12% bottom for captions.
        # Crop *only* those reserved margins; the axes retain the whole
        # statistical image. User-specified title/note replace them below.
        top = int(source_image.height * 0.10)
        bottom = int(source_image.height * 0.925)
        if bottom - top < 50:
            raise ValueError("Original PNG too short to replace its caption.")
        source_image = source_image.crop(
            (0, top, source_image.width, bottom)
        )
    plot_height = min(8.5, max(3.0, source_image.height / source_image.width * 7.25))
    height = plot_height + 2.1
    fig = plt.figure(figsize=(8.5, height), facecolor="white")
    try:
        y_top = 1.0 - 1.16 / height
        y_bottom = 0.77 / height
        ax = fig.add_axes([0.07, y_bottom, 0.86, y_top - y_bottom])
        ax.imshow(source_image)
        ax.set_axis_off()
        fig.text(
            0.07, 1.0 - 0.25 / height, f"Figure {figure_number}",
            ha="left", va="top", fontsize=12, weight="bold",
            fontfamily="DejaVu Sans", color="black",
        )
        short_title = textwrap.fill(" ".join(title.split()), width=78)
        fig.text(
            0.07, 1.0 - 0.62 / height, short_title,
            ha="left", va="top", fontsize=11, style="italic",
            fontfamily="DejaVu Sans", color="black",
        )
        effective_note = note.strip() or DEFAULT_NOTE
        fig.text(
            0.07, 0.58 / height,
            textwrap.fill(effective_note, width=105),
            ha="left", va="top", fontsize=9, fontfamily="DejaVu Sans",
            color="black",
        )
        output = BytesIO()
        fig.savefig(
            output, format="png", dpi=dpi, facecolor="white",
            metadata={
                "Title": f"Figure {figure_number}: {' '.join(title.split())}",
                "Description": effective_note,
                "Software": "Statistical Research Assistant (APA 7-style export)",
            },
        )
        return output.getvalue()
    finally:
        plt.close(fig)
