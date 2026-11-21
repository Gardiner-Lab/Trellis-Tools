"""
Draw the demo lab's floor plan as a PDF, the way an architect's equipment drawing
("afsprakentekening") is laid out: rooms numbered with their name under the number,
and each fridge, freezer, cabinet or machine drawn as a closed outline with the
trade's short label inside it (KK, VR (-80), -20, Kast, FC, BSC, INC, IJS).

Lab Map reads those labels and the outline round each (app/plans.py), so the demo
shows the same "suggested places to accept" that a real drawing gives.
"""
import fitz

W, H = 842, 470
WALL = 2.2
THIN = 0.9
BLACK = (0, 0, 0)

# Three rooms: x0, x1, number, name
ROOMS = [
    (40, 307, '02.2.012', 'Lab 2.12'),
    (307, 574, '02.2.014', 'Cold storage'),
    (574, 802, '02.2.016', 'Plant lab'),
]

# label, x0, y0, x1, y1  (each outline well under MAX_OUTLINE = 220 pt)
THINGS = [
    # Molecular lab
    ('KK', 60, 70, 130, 130),
    ('-20', 150, 70, 220, 130),
    ('Kast', 60, 150, 130, 210),
    ('FC', 150, 150, 240, 215),
    ('INC', 60, 235, 130, 295),
    ('BSC', 150, 235, 250, 300),
    # Cold storage
    ('VR (-80)', 330, 70, 440, 135),
    ('-80', 460, 70, 540, 135),
    ('KK', 330, 160, 400, 220),
    ('IJS', 420, 160, 500, 220),
    ('Kast', 330, 245, 400, 305),
    # Plant lab
    ('INC', 600, 70, 680, 135),
    ('KK', 700, 70, 770, 130),
    ('Kast', 600, 160, 670, 220),
    ('FC', 690, 160, 780, 225),
]


def main(path: str) -> None:
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)

    # Outer wall and the two partitions between the rooms.
    page.draw_rect(fitz.Rect(40, 40, 802, 400), color=BLACK, width=WALL)
    for x in (307, 574):
        page.draw_line(fitz.Point(x, 40), fitz.Point(x, 400), color=BLACK, width=WALL)
    # A doorway in each partition, so the plan reads as rooms rather than boxes.
    for x in (307, 574):
        page.draw_line(fitz.Point(x, 340), fitz.Point(x, 390), color=(1, 1, 1), width=WALL + 1.5)

    # Each room's number with its name underneath, as a drawing labels a room.
    for x0, x1, number, name in ROOMS:
        page.insert_textbox(fitz.Rect(x0 + 12, 325, x1 - 12, 375), f'{number}\n{name}',
                            fontname='helv', fontsize=11, align=fitz.TEXT_ALIGN_CENTER)

    # The equipment: a closed outline with its label inside, which is what Lab Map reads.
    for label, x0, y0, x1, y1 in THINGS:
        page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=BLACK, width=THIN)
        page.insert_textbox(fitz.Rect(x0, (y0 + y1) / 2 - 7, x1, (y0 + y1) / 2 + 9), label,
                            fontname='helv', fontsize=9, align=fitz.TEXT_ALIGN_CENTER)

    page.insert_text(fitz.Point(40, 428), 'Demo Lab — equipment drawing — second floor',
                     fontname='helv', fontsize=10)
    page.insert_text(fitz.Point(40, 446), 'Example plan supplied with the Trellis Tools demo.',
                     fontname='helv', fontsize=8, color=(0.35, 0.35, 0.35))
    doc.save(path)
    print('wrote', path)


if __name__ == '__main__':
    import sys
    main(sys.argv[1])
