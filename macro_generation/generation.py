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

MAX_DEPTH = 32
MARGIN = GAP
# Regions smaller than this use tight packing (larger fraction of remaining space)
SMALL_REGION = 8 * MIN_WIDTH
GRID_FILL_STEP = MIN_WIDTH + GAP
# 0–1: extra min-size tiles in gaps after recursive pass (1 = maximum density)
GRID_FILL_DENSITY = 0.72


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


def size_fractions(depth, inner_w, inner_h):
    """Smaller fractions at shallow depth → more rects; tight pack in tiny regions."""
    if inner_w < SMALL_REGION or inner_h < SMALL_REGION:
        return 0.30, 0.92

    max_frac_by_depth = (0.08, 0.10, 0.12, 0.14, 0.17, 0.20, 0.24)
    min_frac_by_depth = (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09)
    i = min(depth, len(max_frac_by_depth) - 1)
    return min_frac_by_depth[i], max_frac_by_depth[i]


def place_probability(depth, inner_w, inner_h):
    if inner_w < SMALL_REGION or inner_h < SMALL_REGION:
        return 1.0
    return max(0.92, 0.99 - depth * 0.004)


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
    if rw >= rh and rw > 3 * MIN_WIDTH:
        split = snap_size(rw * random.uniform(0.32, 0.68))
        return [
            (rx, ry, split, rh),
            (rx + split + GAP, ry, rw - split - GAP, rh),
        ]
    if rh > 3 * MIN_WIDTH:
        split = snap_size(rh * random.uniform(0.32, 0.68))
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

    if random.random() < place_probability(depth, inner_w, inner_h):
        min_frac, max_frac = size_fractions(depth, inner_w, inner_h)
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


def overlaps_existing(x, y, w, h, rectangles):
    for rx, ry, rw, rh in rectangles:
        if x < rx + rw + GAP and rx < x + w + GAP and y < ry + rh + GAP and ry < y + h + GAP:
            return True
    return False


def grid_fill_gaps(rectangles):
    """Pack minimum-size rects into gaps left by the recursive layout."""
    x = MARGIN
    while x + MIN_WIDTH <= MACRO_W - MARGIN:
        y = MARGIN
        while y + MIN_WIDTH <= MACRO_H - MARGIN:
            w = h = MIN_WIDTH
            if random.random() < GRID_FILL_DENSITY and not overlaps_existing(
                x, y, w, h, rectangles
            ):
                px, py, pw, ph = snap_rect(x, y, w, h)
                rectangles.append((px, py, pw, ph))
            y += GRID_FILL_STEP
        x += GRID_FILL_STEP


def generate_pattern():
    rectangles = []
    fill_region(0, 0, MACRO_W, MACRO_H, 0, rectangles)
    grid_fill_gaps(rectangles)
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
