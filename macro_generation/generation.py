import random

import gdstk

# Sky130 met4 (used as met6 art in prior project)
METAL_LAYER = 71
METAL_DATATYPE = 20

MIN_WIDTH = 1.7
MIN_SPACING = 1.7
GAP = MIN_SPACING
GRID = 0.005  # sky130 / KLayout precheck manufacturing grid

# Right VPWR/VGND in LEF track ~macro_top+10um; need top >= ~206um for precheck (die 225.76um)
MACRO_W = 252.0
MACRO_H = 196.0

MAX_DEPTH = 18
MARGIN = GAP


def snap_coord(value):
    return round(value / GRID) * GRID


def snap_size(value):
    step = MIN_WIDTH
    return max(MIN_WIDTH, round(value / step) * step)


def snap_rect(x, y, w, h):
    x = snap_coord(x)
    y = snap_coord(y)
    w = snap_size(w)
    h = snap_size(h)
    return x, y, w, h


def region_usable(w, h):
    return w >= MIN_WIDTH + 2 * MARGIN and h >= MIN_WIDTH + 2 * MARGIN


def size_fractions(depth):
    """Largest rects stay a modest fraction of their region (not the whole canvas)."""
    max_frac_by_depth = (0.16, 0.20, 0.26, 0.32, 0.38)
    min_frac_by_depth = (0.06, 0.08, 0.10, 0.12, 0.14)
    i = min(depth, len(max_frac_by_depth) - 1)
    return min_frac_by_depth[i], max_frac_by_depth[i]


def place_probability(depth):
    return max(0.5, 0.95 - depth * 0.04)


def l_split_free_regions(rx, ry, rw, rh, px, py, pw, ph):
    """Return non-overlapping free rectangles after placing one rectangle."""
    regions = []

    top_h = py - ry - GAP
    if top_h >= MIN_WIDTH + MARGIN:
        regions.append((rx, ry, rw, top_h))

    bottom_y = py + ph + GAP
    bottom_h = ry + rh - bottom_y
    if bottom_h >= MIN_WIDTH + MARGIN:
        regions.append((rx, bottom_y, rw, bottom_h))

    left_w = px - rx - GAP
    if left_w >= MIN_WIDTH + MARGIN:
        regions.append((rx, py, left_w, ph))

    right_x = px + pw + GAP
    right_w = rx + rw - right_x
    if right_w >= MIN_WIDTH + MARGIN:
        regions.append((right_x, py, right_w, ph))

    return regions


def split_region_without_placing(rx, ry, rw, rh):
    """Guillotine split when we skip placement but still want finer regions."""
    if rw >= rh and rw > 4 * MIN_WIDTH:
        split = snap_size(rw * random.uniform(0.38, 0.62))
        return [
            (rx, ry, split, rh),
            (rx + split + GAP, ry, rw - split - GAP, rh),
        ]
    if rh > 4 * MIN_WIDTH:
        split = snap_size(rh * random.uniform(0.38, 0.62))
        return [
            (rx, ry, rw, split),
            (rx, ry + split + GAP, rw, rh - split - GAP),
        ]
    return [(rx, ry, rw, rh)]


def fill_region(rx, ry, rw, rh, depth, rectangles):
    if depth > MAX_DEPTH or not region_usable(rw, rh):
        return

    inner_w = rw - 2 * MARGIN
    inner_h = rh - 2 * MARGIN

    if random.random() < place_probability(depth):
        min_frac, max_frac = size_fractions(depth)
        pw = snap_size(random.uniform(min_frac, max_frac) * inner_w)
        ph = snap_size(random.uniform(min_frac, max_frac) * inner_h)
        pw = min(pw, inner_w)
        ph = min(ph, inner_h)

        px = rx + MARGIN + random.uniform(0, inner_w - pw)
        py = ry + MARGIN + random.uniform(0, inner_h - ph)
        px, py, pw, ph = snap_rect(px, py, pw, ph)

        rectangles.append((px, py, pw, ph))

        free_regions = l_split_free_regions(rx, ry, rw, rh, px, py, pw, ph)
    else:
        free_regions = split_region_without_placing(rx, ry, rw, rh)

    random.shuffle(free_regions)
    for region in free_regions:
        fill_region(*region, depth + 1, rectangles)


def generate_pattern():
    rectangles = []
    fill_region(0, 0, MACRO_W, MACRO_H, 0, rectangles)
    return rectangles


def add_rectangles_to_cell(cell, rectangles):
    for x, y, w, h in rectangles:
        cell.add(
            gdstk.rectangle(
                (x, y),
                (x + w, y + h),
                layer=METAL_LAYER,
                datatype=METAL_DATATYPE,
            )
        )


def write_lef_file(filename, cell_name, width, height):
    with open(filename, "w") as f:
        f.write(f"# LEF file generated for {cell_name}\n")
        f.write("VERSION 5.8 ;\n")
        f.write("NAMESCASESENSITIVE ON ;\n")
        f.write("DIVIDERCHAR \"/\" ;\n")
        f.write("BUSBITCHARS \"[]\" ;\n")
        f.write("UNITS\n")
        f.write("   DATABASE MICRONS 1000 ;\n")
        f.write("END UNITS\n\n")
        f.write(f"MACRO {cell_name}\n")
        f.write("   CLASS BLOCK ;\n")
        f.write(f"   FOREIGN {cell_name} 0 0 ;\n")
        f.write(f"   SIZE {width:.3f} BY {height:.3f} ;\n")
        f.write("   SYMMETRY X Y ;\n")
        f.write(f"END {cell_name}\n")


lib = gdstk.Library()
cell = lib.new_cell("my_logo")

rectangles = generate_pattern()
add_rectangles_to_cell(cell, rectangles)

pr_boundary = gdstk.rectangle((0, 0), (MACRO_W, MACRO_H), layer=235, datatype=4)
cell.add(pr_boundary)

write_lef_file("../macros/my_logo.lef", "my_logo", MACRO_W, MACRO_H)
lib.write_gds("../macros/my_logo.gds")
cell.write_svg("../macros/my_logo.svg")

print(f"Placed {len(rectangles)} rectangles in {MACRO_W}x{MACRO_H} µm macro")
