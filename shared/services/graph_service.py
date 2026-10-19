from io import BytesIO
import base64
from flask import render_template

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from shared.models import Exam, Mark
from shared.services.course_service import course_name


def generate_graph(roll_no, subject, exam_id, department=None, year=None, sec=None, bg="#1565A6"):
    try:
        exam_all = Exam.query.order_by(Exam.exam_id).all()

        mark = Mark.query.filter(
            Mark.roll_no == roll_no,
            Mark.subject == subject
        ).all()

        exam = Exam.query.filter(Exam.exam_id == exam_id).first()
        exam1 = exam.exam_name

        # Seaborn Theme
        sns.set_theme(style="white")

        # Create Figure
        fig, ax = plt.subplots(figsize=(12, 6))

        # Background Color (bg is a parameter; default is the blue theme)
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        # Grid
        ax.grid(
            True,
            color="white",
            linewidth=0.8,
            alpha=0.35
        )

        ax.minorticks_on()

        ax.grid(
            which="minor",
            color="white",
            linewidth=0.4,
            alpha=0.25
        )

        by_exam = {m.exam_id: m.marks for m in mark if m.marks}  # skip "not entered" (0)
        df = pd.DataFrame({
            "Exam": [e.exam_name for e in exam_all if e.exam_id in by_exam],
            "Marks": [by_exam[e.exam_id] for e in exam_all if e.exam_id in by_exam],
        })

        # Line Plot (Seaborn)
        sns.lineplot(
            data=df,
            x="Exam",
            y="Marks",
            color="white",
            linewidth=3,
            marker="o",
            markersize=9,
            ax=ax
        )

        # Fill Area
        ax.fill_between(
            df["Exam"],
            df["Marks"],
            color="white",
            alpha=0.18
        )

        # Axis Styling
        ax.tick_params(colors="white", labelsize=12)

        for spine in ax.spines.values():
            spine.set_color("white")
            spine.set_alpha(0.5)

        # Labels
        plt.title(
            f"Student Performance {roll_no}",
            fontsize=22,
            color="white",
            weight="bold",
            pad=20
        )

        plt.xlabel(
            f"Exam {exam1}",
            fontsize=14,
            color="white"
        )

        plt.ylabel(
            f"{course_name(subject)} Marks",
            fontsize=14,
            color="white"
        )

        # Value Labels
        for x, y in zip(df["Exam"], df["Marks"]):
            plt.text(
                x,
                y + 2,
                str(y),
                color="white",
                fontsize=11,
                ha="center"
            )

        plt.ylim(0, 100)

        sns.despine(left=False, bottom=False)

        plt.tight_layout()
        buffer = BytesIO()

        plt.savefig(
            buffer,
            format="png",
            facecolor=bg,
            bbox_inches="tight",
            pad_inches=0.3
        )

        buffer.seek(0)

        graph_base64 = base64.b64encode(buffer.getvalue()).decode()

        plt.close()

        return graph_base64, exam1
    except Exception as e:
       print(f'ERROR:{e}')
       return render_template("Error.html",data="Enter the marks for all the subject to display",location="/home")


def generate_pie_graph(roll_no, exam_id, department=None, year=None, sec=None, bg="#1565A6"):
    try:
        exam = Exam.query.filter(Exam.exam_id == exam_id).first()
        exam1 = exam.exam_name

        mark = (
            Mark.query.filter(
                Mark.roll_no == roll_no,
                Mark.exam_id == exam_id
            )
            .all()
        )

        if not mark:
            raise ValueError("No marks found.")

        if any(m.marks == 0 for m in mark):
            raise ValueError(
                "Enter the marks for all subjects to display the graph."
            )

        labels = [course_name(m.subject) for m in mark]
        values = [m.marks for m in mark]

        # Seaborn Theme
        sns.set_theme(style="white")

        # Create Figure
        fig, ax = plt.subplots(figsize=(8, 8))

        # Background Color (bg is a parameter; default is the blue theme)
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(bg)

        colors = sns.color_palette("pastel", len(labels))

        # Pie Chart
        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90,
            radius=1.15,
            colors=colors,
            textprops={"color": "white", "fontsize": 13},
            wedgeprops={"edgecolor": bg, "linewidth": 2}
        )

        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_fontsize(12)
            autotext.set_weight("bold")

        # Labels
        plt.title(
            f"Total Marks Breakdown {roll_no}",
            fontsize=22,
            color="white",
            weight="bold",
            pad=12
        )

        ax.axis("equal")

        plt.tight_layout()
        buffer = BytesIO()

        plt.savefig(
            buffer,
            format="png",
            facecolor=bg,
            bbox_inches="tight",
            pad_inches=0.3
        )

        buffer.seek(0)

        graph_base64 = base64.b64encode(buffer.getvalue()).decode()

        plt.close()

        return graph_base64, exam1
    except Exception as e:
       print(f'ERROR:{e}')
       return render_template("Error.html",data="Enter the marks for all the subject to display",location="/home")