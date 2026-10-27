import math
import os
import struct
import zlib


DESIGN_SIZE = 512
SCALE = 2
SIZE = DESIGN_SIZE * SCALE


class Canvas:
    def __init__(self, size):
        self.size = size
        self.scale = size // DESIGN_SIZE
        self.pixels = bytearray(size * size * 4)

    def set_pixel(self, x, y, color):
        if 0 <= x < self.size and 0 <= y < self.size:
            offset = (y * self.size + x) * 4
            self.pixels[offset:offset + 4] = bytes(color)

    def polygon(self, points, color):
        points = [(round(x * self.scale), round(y * self.scale)) for x, y in points]
        min_y = max(0, min(point[1] for point in points))
        max_y = min(self.size - 1, max(point[1] for point in points))
        rgba = bytes(color)

        for y in range(min_y, max_y + 1):
            intersections = []
            previous = points[-1]
            for current in points:
                if (current[1] > y) != (previous[1] > y):
                    x = ((previous[0] - current[0]) * (y - current[1]) /
                         (previous[1] - current[1]) + current[0])
                    intersections.append(x)
                previous = current

            intersections.sort()
            row_start = y * self.size * 4
            for index in range(0, len(intersections) - 1, 2):
                start = max(0, math.ceil(intersections[index]))
                end = min(self.size - 1, math.floor(intersections[index + 1]))
                if end >= start:
                    offset = row_start + start * 4
                    self.pixels[offset:offset + (end - start + 1) * 4] = rgba * (end - start + 1)

    def ellipse(self, cx, cy, rx, ry, color):
        cx, cy, rx, ry = (round(value * self.scale) for value in (cx, cy, rx, ry))
        min_x = max(0, cx - rx)
        max_x = min(self.size - 1, cx + rx)
        min_y = max(0, cy - ry)
        max_y = min(self.size - 1, cy + ry)
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                dx = (x - cx) / rx
                dy = (y - cy) / ry
                if dx * dx + dy * dy <= 1:
                    self.set_pixel(x, y, color)

    def line(self, start, end, color, width):
        x0, y0 = start
        x1, y1 = end
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(steps + 1):
            t = step / steps
            x = round(x0 + (x1 - x0) * t)
            y = round(y0 + (y1 - y0) * t)
            self.ellipse(x, y, width, width, color)

    def save(self, path, textured=False):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if textured:
            for tile_y in range(0, self.size, self.scale * 2):
                for tile_x in range(0, self.size, self.scale * 2):
                    variation = ((tile_x * 17 + tile_y * 29 +
                                  (tile_x * tile_y // 7)) % 17) - 8
                    for y in range(tile_y, min(self.size, tile_y + self.scale * 2)):
                        for x in range(tile_x, min(self.size, tile_x + self.scale * 2)):
                            offset = (y * self.size + x) * 4
                            if self.pixels[offset + 3]:
                                for channel in range(3):
                                    self.pixels[offset + channel] = max(
                                        0, min(255, self.pixels[offset + channel] + variation))

        raw = bytearray()
        stride = self.size * 4
        for row in range(self.size):
            raw.append(0)
            raw.extend(self.pixels[row * stride:(row + 1) * stride])

        def chunk(kind, data):
            return (struct.pack(">I", len(data)) + kind + data +
                    struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

        png = (b"\x89PNG\r\n\x1a\n" +
               chunk(b"IHDR", struct.pack(">2I5B", self.size, self.size, 8, 6, 0, 0, 0)) +
               chunk(b"IDAT", zlib.compress(raw, 9)) +
               chunk(b"IEND", b""))
        with open(path, "wb") as image:
            image.write(png)


def make_sidearm(path):
    image = Canvas(SIZE)
    dark = (18, 26, 34, 255)
    body = (48, 66, 76, 255)
    steel = (111, 139, 146, 255)
    edge = (178, 203, 197, 255)
    cyan = (76, 235, 223, 255)
    amber = (240, 167, 94, 255)

    image.polygon([(73, 267), (111, 221), (323, 147), (402, 163),
                   (421, 211), (361, 252), (245, 283), (201, 343),
                   (166, 409), (112, 398), (141, 316)], dark)
    image.polygon([(100, 269), (126, 237), (324, 173), (385, 184),
                   (393, 210), (346, 231), (235, 260), (181, 326),
                   (149, 380), (136, 375), (161, 307)], body)
    image.polygon([(133, 241), (323, 180), (359, 185), (349, 206),
                   (170, 260)], steel)
    image.polygon([(310, 170), (397, 151), (436, 164), (451, 186),
                   (427, 199), (367, 193)], dark)
    image.polygon([(324, 178), (395, 162), (424, 169), (434, 184),
                   (414, 189), (367, 184)], edge)
    image.polygon([(191, 274), (258, 256), (242, 295), (208, 322),
                   (184, 314)], dark)
    image.polygon([(219, 284), (243, 277), (229, 298), (211, 307)], amber)
    image.polygon([(127, 315), (178, 329), (160, 386), (144, 390),
                   (120, 374)], steel)
    image.line((150, 344), (137, 374), edge, 5)
    image.polygon([(80, 268), (102, 255), (121, 267), (113, 289),
                   (91, 294)], cyan)
    image.ellipse(101, 274, 7, 7, (222, 255, 247, 255))
    image.line((176, 247), (290, 210), edge, 3)
    image.line((185, 254), (258, 232), cyan, 4)
    image.line((255, 276), (295, 268), edge, 3)
    image.save(path)


def make_pulse_carbine(path):
    image = Canvas(SIZE)
    dark = (18, 25, 31, 255)
    body = (47, 63, 71, 255)
    steel = (101, 128, 137, 255)
    edge = (166, 192, 190, 255)
    cyan = (64, 214, 206, 255)
    amber = (230, 159, 91, 255)

    image.polygon([(42, 285), (96, 235), (274, 184), (400, 157),
                   (459, 168), (483, 190), (466, 211), (399, 220),
                   (306, 246), (255, 275), (225, 329), (173, 383),
                   (116, 380), (137, 327), (91, 312)], dark)
    image.polygon([(78, 279), (116, 245), (279, 199), (401, 174),
                   (447, 181), (455, 194), (395, 203), (299, 230),
                   (242, 259), (210, 313), (168, 358), (137, 359),
                   (154, 319), (113, 301)], body)
    image.polygon([(123, 247), (278, 204), (395, 180), (425, 185),
                   (397, 195), (285, 221), (157, 260)], steel)
    image.polygon([(394, 173), (450, 161), (475, 169), (488, 187),
                   (465, 198), (406, 197)], dark)
    image.polygon([(410, 177), (450, 169), (469, 174), (477, 186),
                   (459, 190), (410, 190)], edge)
    image.polygon([(37, 272), (73, 250), (119, 264), (112, 296),
                   (75, 305), (42, 292)], dark)
    image.polygon([(51, 273), (74, 263), (103, 270), (99, 286),
                   (75, 294), (52, 287)], body)
    image.line((56, 276), (92, 274), edge, 4)
    image.polygon([(201, 259), (250, 244), (269, 258), (254, 279),
                   (229, 289), (207, 278)], dark)
    image.polygon([(220, 263), (248, 254), (255, 260), (245, 271),
                   (225, 278)], amber)
    image.polygon([(284, 229), (315, 220), (307, 252), (292, 265)], dark)
    image.polygon([(292, 231), (305, 227), (300, 245), (294, 249)], cyan)
    image.polygon([(154, 317), (202, 326), (181, 384), (152, 400),
                   (119, 383), (130, 345)], dark)
    image.polygon([(158, 328), (189, 334), (172, 377), (154, 385),
                   (137, 375), (144, 347)], steel)
    image.line((150, 345), (164, 351), edge, 4)
    image.line((180, 246), (270, 220), cyan, 4)
    image.line((273, 211), (330, 197), edge, 3)
    image.line((360, 192), (386, 186), amber, 3)
    image.save(path)


def make_field_agent_arms(path):
    image = Canvas(SIZE)
    sleeve = (35, 51, 61, 255)
    sleeve_light = (74, 95, 101, 255)
    cuff = (80, 94, 91, 255)
    glove = (25, 31, 34, 255)
    glove_light = (70, 78, 76, 255)
    seam = (132, 146, 137, 255)

    image.polygon([(326, 512), (512, 512), (512, 352), (467, 329),
                   (409, 335), (347, 382), (297, 435)], sleeve)
    image.polygon([(362, 512), (512, 512), (512, 368), (469, 349),
                   (423, 355), (369, 401), (325, 448)], sleeve_light)
    image.line((357, 480), (418, 402), seam, 4)
    image.line((388, 494), (446, 421), (47, 69, 77, 255), 4)
    image.polygon([(246, 387), (279, 370), (328, 389), (358, 430),
                   (343, 462), (307, 477), (266, 447)], cuff)
    image.line((266, 408), (334, 430), seam, 4)
    image.polygon([(179, 338), (211, 312), (248, 316), (279, 341),
                   (284, 370), (263, 392), (226, 375), (204, 363)], glove)
    image.polygon([(202, 341), (221, 325), (247, 331), (262, 349),
                   (248, 360), (226, 353)], glove_light)
    image.polygon([(239, 360), (276, 345), (295, 357), (290, 378),
                   (268, 386), (248, 378)], glove)
    image.line((211, 347), (249, 351), (117, 129, 119, 255), 3)
    image.save(path)


def make_security_guard(path, style=0):
    image = Canvas(SIZE)
    palettes = [
        ((42, 57, 57, 255), (71, 88, 80, 255), (31, 42, 38, 255),
         (93, 65, 48, 255), (189, 139, 104, 255), (67, 46, 39, 255),
         (151, 106, 79, 255), (201, 164, 124, 255)),
        ((51, 57, 68, 255), (83, 94, 105, 255), (34, 40, 48, 255),
         (112, 69, 49, 255), (224, 184, 145, 255), (64, 42, 34, 255),
         (65, 77, 82, 255), (159, 174, 174, 255)),
        ((52, 62, 51, 255), (87, 99, 69, 255), (37, 44, 33, 255),
         (110, 75, 51, 255), (204, 158, 118, 255), (51, 39, 31, 255),
         (79, 93, 62, 255), (178, 160, 117, 255)),
        ((72, 66, 54, 255), (109, 95, 73, 255), (44, 41, 35, 255),
         (87, 57, 42, 255), (174, 119, 87, 255), (43, 31, 28, 255),
         (91, 81, 62, 255), (194, 174, 135, 255)),
        ((45, 58, 73, 255), (79, 94, 112, 255), (30, 39, 52, 255),
         (116, 76, 53, 255), (216, 176, 137, 255), (83, 48, 32, 255),
         (60, 80, 100, 255), (158, 179, 190, 255)),
        ((59, 51, 60, 255), (96, 80, 93, 255), (38, 34, 42, 255),
         (105, 73, 53, 255), (196, 151, 116, 255), (50, 39, 34, 255),
         (78, 67, 79, 255), (176, 157, 144, 255)),
    ]
    coat, coat_light, trouser, skin, skin_light, hair, accessory, thread = palettes[style]
    dark = (27, 31, 32, 255)
    boots = (31, 31, 29, 255)
    eye = (39, 37, 34, 255)
    hair_style = (0, 1, 2, 3, 4, 5)[style]

    # Boots, separated trousers and visible cloth seams give the sprite a human silhouette.
    image.polygon([(177, 424), (245, 420), (238, 486), (219, 497),
                   (169, 486), (150, 463)], dark)
    image.polygon([(267, 420), (335, 424), (362, 463), (343, 486),
                   (293, 497), (274, 486)], dark)
    image.polygon([(183, 430), (240, 426), (231, 479), (212, 486),
                   (168, 474), (161, 461)], trouser)
    image.polygon([(272, 426), (329, 430), (351, 461), (344, 474),
                   (300, 486), (281, 479)], coat_light)
    image.line((204, 438), (196, 472), thread, 3)
    image.line((302, 438), (310, 472), thread, 3)
    image.polygon([(174, 474), (220, 481), (218, 497), (158, 503),
                   (145, 492)], boots)
    image.polygon([(291, 481), (338, 474), (368, 492), (356, 503),
                   (296, 497)], boots)
    image.line((167, 490), (208, 488), (95, 90, 83, 255), 3)
    image.line((305, 488), (348, 490), (95, 90, 83, 255), 3)

    # Sleeves, relaxed hands, and a tailored uniform keep the equipment secondary to the person.
    image.polygon([(139, 281), (188, 265), (216, 301), (202, 362),
                   (188, 407), (166, 426), (145, 407), (154, 350)], dark)
    image.polygon([(373, 281), (324, 265), (296, 301), (310, 362),
                   (324, 407), (346, 426), (367, 407), (358, 350)], dark)
    image.polygon([(148, 286), (187, 276), (204, 305), (190, 355),
                   (178, 397), (164, 408), (153, 389), (162, 345)], coat)
    image.polygon([(364, 286), (325, 276), (308, 305), (322, 355),
                   (334, 397), (348, 408), (359, 389), (350, 345)], coat_light)
    image.line((163, 308), (181, 321), thread, 4)
    image.line((349, 308), (331, 321), thread, 4)
    image.polygon([(151, 373), (177, 382), (171, 414), (154, 421),
                   (143, 405)], skin)
    image.polygon([(361, 373), (335, 382), (341, 414), (358, 421),
                   (369, 405)], skin_light)
    image.line((151, 396), (159, 405), (118, 81, 65, 255), 3)
    image.line((361, 396), (353, 405), (139, 98, 75, 255), 3)

    # Jacket with a collar, stitched panels, belt, and practical field pouches.
    image.polygon([(175, 271), (211, 250), (301, 250), (337, 271),
                   (352, 397), (319, 431), (193, 431), (160, 397)], dark)
    image.polygon([(183, 275), (215, 260), (251, 271), (249, 418),
                   (197, 415), (170, 392)], coat_light)
    image.polygon([(257, 271), (297, 260), (329, 275), (342, 392),
                   (315, 415), (257, 418)], coat)
    image.polygon([(224, 263), (249, 274), (257, 274), (282, 263),
                   (270, 292), (251, 302), (234, 291)], thread)
    image.line((251, 303), (253, 394), (37, 41, 40, 255), 3)
    image.line((194, 307), (188, 379), thread, 3)
    image.line((311, 307), (318, 379), thread, 3)
    image.polygon([(184, 325), (224, 318), (231, 352), (187, 357)], accessory)
    image.polygon([(277, 318), (318, 325), (315, 357), (270, 352)], accessory)
    image.line((191, 332), (219, 327), thread, 3)
    image.line((282, 327), (311, 332), thread, 3)
    image.polygon([(192, 365), (228, 360), (232, 388), (188, 389)], coat)
    image.polygon([(276, 360), (312, 365), (316, 389), (272, 388)], coat_light)
    image.line((199, 371), (224, 370), thread, 2)
    image.line((278, 370), (307, 371), thread, 2)
    image.polygon([(190, 400), (311, 400), (320, 423), (297, 431),
                   (202, 431), (181, 423)], dark)
    image.line((195, 407), (306, 407), thread, 3)
    image.ellipse(250, 415, 6, 7, (171, 148, 107, 255))
    image.polygon([(211, 412), (237, 412), (237, 430), (214, 428)], accessory)
    image.polygon([(268, 412), (294, 412), (291, 428), (268, 430)], accessory)
    image.line((214, 418), (234, 418), thread, 2)
    image.line((272, 418), (290, 418), thread, 2)
    image.polygon([(193, 277), (207, 269), (224, 286), (215, 296)], thread)
    image.polygon([(308, 277), (294, 269), (278, 286), (287, 296)], thread)
    image.ellipse(206, 292, 4, 4, accessory)
    image.ellipse(297, 292, 4, 4, accessory)

    # Neck, ears, open face, eyes, nose and mouth: uncovered human features rather than a robot visor.
    image.polygon([(230, 226), (278, 226), (282, 266), (258, 280),
                   (232, 266)], (110, 73, 55, 255))
    image.ellipse(197, 147, 12, 21, skin)
    image.ellipse(303, 147, 12, 21, (145, 95, 68, 255))
    image.ellipse(256, 160, 62, 79, (69, 45, 37, 255))
    image.ellipse(256, 155, 56, 72, skin)
    image.polygon([(201, 140), (216, 105), (245, 85), (278, 89),
                   (306, 112), (312, 139), (297, 130), (284, 111),
                   (258, 123), (228, 119)], hair)
    image.polygon([(210, 130), (221, 108), (244, 96), (272, 99),
                   (291, 115), (278, 122), (257, 116), (235, 127)], skin_light)
    image.polygon([(205, 148), (225, 140), (244, 146), (244, 153),
                   (226, 150), (211, 154)], hair)
    image.polygon([(267, 146), (286, 140), (304, 150), (297, 154),
                   (278, 150), (268, 153)], hair)
    image.ellipse(229, 158, 4, 3, (216, 198, 177, 255))
    image.ellipse(282, 158, 4, 3, (216, 198, 177, 255))
    image.ellipse(231, 158, 1, 2, eye)
    image.ellipse(283, 158, 1, 2, eye)
    image.line((219, 145), (239, 143), hair, 3)
    image.line((273, 143), (294, 146), hair, 3)
    image.polygon([(249, 161), (243, 185), (252, 190), (262, 186),
                   (256, 161)], (163, 105, 75, 255))
    image.line((251, 184), (256, 186), (112, 72, 55, 255), 2)
    image.line((238, 200), (253, 203), (112, 63, 54, 255), 2)
    image.line((255, 203), (271, 199), (112, 63, 54, 255), 2)
    image.polygon([(230, 215), (254, 222), (277, 214), (270, 230),
                   (253, 237), (237, 230)], (139, 81, 63, 255))
    image.line((240, 220), (253, 222), skin_light, 3)

    # Each original guard has distinct headwear and grooming, never an opaque faceplate.
    if hair_style == 0:
        image.polygon([(197, 133), (196, 111), (222, 91), (283, 91),
                       (310, 111), (313, 134), (292, 119), (279, 108),
                       (231, 109), (212, 125)], (55, 61, 57, 255))
        image.line((202, 124), (305, 122), (126, 132, 117, 255), 3)
    elif hair_style == 1:
        image.polygon([(199, 134), (198, 112), (222, 88), (279, 87),
                       (311, 110), (308, 131), (291, 112), (268, 104),
                       (232, 107), (214, 125)], hair)
        image.line((207, 124), (300, 122), (174, 168, 175, 255), 3)
        image.ellipse(307, 150, 7, 7, (172, 158, 139, 255))
    elif hair_style == 2:
        image.polygon([(194, 137), (198, 108), (219, 85), (282, 82),
                       (314, 108), (319, 139), (298, 126), (288, 102),
                       (222, 104), (210, 132)], (74, 80, 62, 255))
        image.polygon([(193, 134), (220, 126), (284, 123), (316, 133),
                       (310, 147), (199, 150)], (102, 108, 78, 255))
        image.line((218, 136), (286, 134), thread, 3)
    elif hair_style == 3:
        image.polygon([(191, 148), (198, 113), (228, 86), (278, 86),
                       (313, 117), (319, 146), (300, 128), (283, 101),
                       (222, 104), (208, 150)], (72, 67, 56, 255))
        image.polygon([(191, 141), (226, 132), (282, 130), (321, 139),
                       (311, 149), (202, 151)], (126, 111, 82, 255))
    elif hair_style == 4:
        image.polygon([(196, 133), (197, 110), (225, 88), (281, 88),
                       (311, 111), (313, 133), (292, 121), (282, 105),
                       (230, 106), (212, 127)], (60, 70, 82, 255))
        image.line((204, 122), (306, 121), (157, 176, 190, 255), 3)
        image.ellipse(309, 164, 8, 10, accessory)
        image.ellipse(311, 164, 4, 5, thread)
        image.line((313, 171), (322, 176), (58, 62, 68, 255), 3)
    else:
        image.polygon([(192, 142), (198, 111), (225, 83), (283, 83),
                       (316, 108), (321, 141), (299, 128), (286, 104),
                       (222, 105), (207, 143)], (56, 48, 55, 255))
        image.polygon([(188, 135), (228, 126), (281, 126), (322, 137),
                       (319, 147), (193, 147)], (99, 86, 77, 255))
        image.line((198, 137), (311, 138), (177, 150, 142, 255), 3)

    # A grounded, clearly identifiable firearm held at the hip instead of a glowing toy rifle.
    image.polygon([(281, 312), (298, 306), (365, 331), (357, 346),
                   (325, 344), (282, 328)], dark)
    image.polygon([(328, 324), (344, 321), (389, 338), (384, 347),
                   (367, 349), (333, 339)], (70, 73, 69, 255))
    image.line((345, 329), (381, 342), (144, 139, 119, 255), 3)
    image.polygon([(382, 335), (424, 338), (444, 347), (425, 352),
                   (385, 349)], dark)
    image.polygon([(292, 326), (312, 331), (305, 352), (295, 351)],
                  (52, 51, 47, 255))
    image.polygon([(381, 337), (397, 338), (395, 345), (380, 344)], thread)
    image.save(path, textured=True)


def main():
    directory = os.path.dirname(os.path.abspath(__file__))
    characters = os.path.join(directory, "characters")
    weapons = os.path.join(directory, "weapons")
    make_sidearm(os.path.join(weapons, "ion_sidearm.png"))
    make_pulse_carbine(os.path.join(weapons, "pulse_carbine.png"))
    make_field_agent_arms(os.path.join(characters, "field_agent_arms.png"))
    security_roles = (
        "harbor_guard",
        "signal_officer",
        "ground_crew",
        "armored_breacher",
        "perimeter_scout",
        "watch_commander",
    )
    for style, role in enumerate(security_roles):
        make_security_guard(os.path.join(characters, role + ".png"), style)


if __name__ == "__main__":
    main()
