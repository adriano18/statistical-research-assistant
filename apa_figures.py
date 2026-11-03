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


def make_apa7_export_png(
    original_png: bytes, title: str, *,
    figure_number: int = 1, note: str = DEFAULT_NOTE,
    dpi: int = 300,
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
