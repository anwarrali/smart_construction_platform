"""Design-to-execution concept diagram (Figure 1.1), drawn with explicit
coordinates so that no connector crosses another.

Regenerate: python 00_concept.py  ->  ../png/00_concept.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BLUE_EDGE, BLUE_FILL, GREY_EDGE, GREY_FILL, INK = "#2C5F8A", "#EAF1F8", "#7F8C8D", "#FBFCFD", "#34495E"
plt.rcParams["font.family"] = "Arial"

fig, ax = plt.subplots(figsize=(9.6, 6.4), dpi=200)
ax.set_xlim(0, 96)
ax.set_ylim(0, 64)
ax.axis("off")

ROW_H, TOP = 8.2, 52.5          # row pitch and y of row 1 centre
rows = {i: TOP - (i - 1) * ROW_H for i in range(1, 7)}


def box(x, y_top, w, h, text, fill="#FFFFFF", edge=BLUE_EDGE, bold=False, size=9.5):
    ax.add_patch(FancyBboxPatch((x, y_top - h), w, h, boxstyle="round,pad=0.25,rounding_size=0.8",
                                linewidth=1.0, edgecolor=edge, facecolor=fill))
    ax.text(x + w / 2, y_top - h / 2, text, ha="center", va="center", fontsize=size, color="#1B2631",
            fontweight="bold" if bold else "normal", linespacing=1.25)


def lane(x, w, title):
    ax.add_patch(FancyBboxPatch((x, 2.0), w, 57.5, boxstyle="round,pad=0.2,rounding_size=1.2",
                                linewidth=1.0, edgecolor=GREY_EDGE, facecolor=GREY_FILL))
    ax.text(x + w / 2, 61.2, title, ha="center", va="center", fontsize=11, fontweight="bold", color="#1B2631")


def arrow(x1, x2, y, label=None, dashed=False):
    ax.annotate("", xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.1, mutation_scale=11,
                                linestyle=(0, (4, 3)) if dashed else "solid"))
    if label:
        ax.text((x1 + x2) / 2, y + 1.05, label, ha="center", va="bottom", fontsize=7.8, color=INK)


lane(1.0, 21, "Design information")
lane(31.0, 30, "Constructs integration mechanisms")
lane(70.0, 25, "Project execution")

H = 6.2
def top(i):
    return rows[i] + H / 2

# left column: IFC spans rows 1-3
box(3.0, top(1), 17, top(1) - (rows[3] - H / 2), "IFC model\nrevisions", fill=BLUE_FILL)
box(3.0, top(4), 17, H, "Design changes,\nowner requests", fill=BLUE_FILL)
box(3.0, top(5), 17, H, "Site reports, photos,\nvoice notes", fill=BLUE_FILL)
box(3.0, top(6), 17, H, "Contracts, specs,\ndrawings (PDF/Office)", fill=BLUE_FILL)

mech = {
    1: "Coordination findings\n(interference candidates)",
    2: "Task and milestone suggestions\n(generated on processing)",
    3: "Revision comparison and\nimpact suggestions",
    4: "Design change linked\nto a task (task_id)",
    5: "Voice-to-action\n(confirmed drafts)",
    6: "Grounded document answers\n(RAG with citations)",
}
for i, text in mech.items():
    box(33.0, top(i), 26, H, text)

# right column: tasks span rows 2-5
box(72.0, top(1), 21, H, "Issues and reviews", fill=BLUE_FILL)
box(72.0, top(2), 21, top(2) - (rows[5] - H / 2), "Tasks, dependencies\nand CPM schedule", fill=BLUE_FILL)
box(72.0, top(6), 21, H, "Engineer / PM\ndecisions", fill=BLUE_FILL)

for i in range(1, 7):
    arrow(20.6, 32.6, rows[i])
labels = {1: ("create issue", False), 2: ("accept: create", False), 3: ("acknowledge /\ndismiss", False),
          4: ("linked", False), 5: ("progress, issues", False), 6: ("informs", True)}
for i, (lab, dashed) in labels.items():
    arrow(59.6, 71.6, rows[i], lab, dashed)

out = Path(__file__).resolve().parent.parent / "png" / "00_concept.png"
fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
print("saved", out)
