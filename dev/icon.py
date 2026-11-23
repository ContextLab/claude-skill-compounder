#!/usr/bin/env python3
"""Writes the plugin's icon as SVG on standard output.

    python3 dev/icon.py | rsvg-convert -w 1024 -o .claude-plugin/icon.png

The mark is four diamonds set as one diamond, after the glyph the band signs itself with.
Three are solid: something built, something learned, something reused. The fourth holds
the whole mark again, and that one's fourth holds it once more; the innermost fourth tile
is left a shade lighter than its panel, for the round that has not happened yet.

Standard library only. The numbers are positions on a 1024 grid.
"""

GROUND, EDGE = "#101820", "#536170"
LEFT, BOTTOM, RIGHT = "#40D9ED", "#71DF98", "#E68ADD"
PANEL, NEXT = "#304652", "#5B7686"
REACH = 204.5    # from the mark's center to a tile's center
HALF = 187.5     # from a tile's center to its corner
RADIUS = 28
SHRINK = 0.38    # the mark inside the top tile, relative to the mark around it
REPEATS = 2
CENTER = (512, 504)   # a little above the middle: the three solid tiles sit low


def tile(cx, cy, half, fill, radius):
    side = half * 2 ** 0.5
    return ('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="%.2f" fill="%s" '
            'transform="rotate(45 %.2f %.2f)"/>'
            % (cx - side / 2, cy - side / 2, side, side, radius, fill, cx, cy))


def mark(cx, cy, scale, repeats):
    reach, half, radius = REACH * scale, HALF * scale, RADIUS * scale
    shapes = [tile(cx - reach, cy, half, LEFT, radius),
              tile(cx, cy + reach, half, BOTTOM, radius),
              tile(cx + reach, cy, half, RIGHT, radius)]
    if repeats == 0:
        return shapes + [tile(cx, cy - reach, half, NEXT, radius)]
    return (shapes + [tile(cx, cy - reach, half, PANEL, radius)]
            + mark(cx, cy - reach, scale * SHRINK, repeats - 1))


def svg():
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">',
             '<rect x="32" y="32" width="960" height="960" rx="208" fill="%s"/>' % EDGE,
             '<rect x="40" y="40" width="944" height="944" rx="200" fill="%s"/>' % GROUND]
    return "\n".join(lines + mark(CENTER[0], CENTER[1], 1.0, REPEATS) + ["</svg>"]) + "\n"


if __name__ == "__main__":
    print(svg(), end="")
