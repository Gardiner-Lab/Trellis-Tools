"""
Draw the inside of the demo lab's -80 freezer: five towers of shelves, as a photograph of the
open freezer or the rack plan from its maker would show them.

Lab Map takes a picture like this as the map of what is inside a place (demo/load.py marks the
towers on it), so clicking the freezer on the floor plan opens its towers.
"""
from PIL import Image, ImageDraw

W, H = 1000, 760
TOWERS = 5
SHELVES = 9


def main(path: str) -> None:
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, W - 40, H - 40], outline='black', width=6)      # the freezer's walls
    left, top, bottom = 70, 80, H - 80
    width = (W - 140) // TOWERS
    for i in range(TOWERS):
        x0 = left + i * width + 6
        x1 = x0 + width - 14
        d.rectangle([x0, top, x1, bottom], outline='black', width=3)
        for s in range(1, SHELVES):
            y = top + s * (bottom - top) // SHELVES
            d.line([x0, y, x1, y], fill='#555555', width=2)
        d.text((x0 + 18, bottom + 14), f'Tower {i + 1}', fill='black')
    d.text((44, 12), 'Demo Lab  -  -80 C freezer 1  -  inside', fill='black')
    img.save(path)
    print('wrote', path)


if __name__ == '__main__':
    import sys
    main(sys.argv[1])
