/* tracks.c : track definitions (spline control points) + procedural mesh building
 *
 * Each track is a closed Catmull-Rom spline through control points
 * {x, z, height, road width}. The game resamples it every ~2 units and builds
 * a handful of static meshes (road, ground, walls, scenery, sky) once at load,
 * so a whole track costs only ~5 draw calls per frame.
 */
#include "common.h"

const TrackDef TRACK_DEFS[NUM_TRACKS] = {
    {
        .name = "Sunny Meadow Circuit", .subtitle = "Rolling hills, windmills and a sneaky jump",
        .numPts = 21,
        .pts = { {0,-40,0,22}, {0,60,0,22}, {10,135,0,22}, {55,182,1,22}, {125,190,2,22}, {178,155,2,22}, {175,98,1,22}, {125,72,0,22}, {100,30,0,22}, {118,-14,0,22}, {175,-24,0,22}, {225,10,0,22}, {255,70,0,22}, {300,98,0,22}, {348,60,0,22}, {348,-25,0,22}, {300,-88,0,22}, {220,-118,0,22}, {130,-127,0,22}, {60,-117,0,22}, {15,-97,0,22} },
        .scenery = SCENERY_MEADOW,
        .skyTop = {28,104,240,255}, .skyBottom = {150,205,255,255}, .fog = {172,212,250,255},
        .ground = {72,186,52,255}, .road = {146,146,156,255}, .rumbleA = {230,40,40,255}, .rumbleB = {250,250,250,255},
        .wallA = {250,250,250,255}, .wallB = {40,120,230,255},
        .fogDensity = 0.0035f, .grip = 1.0f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.3f,
        .numRamps = 1, .ramps = { {0.74f, 14.0f} },
        .numBoxRows = 3, .boxRows = { 0.08f, 0.45f, 0.84f },
        .scFrom = 0.383f, .scTo = 0.52f, .scSide = 1, .scIsRoad = false, .scHint = "Shortcut: a gap in the fence cuts across the meadow - pepper through the grass!",
        .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .groundFar = {52,152,46,255}, .farStart = 25, .farEnd = 120,
        .musicSeed = 11, .bpm = 150, .musicKey = 60, .musicScale = 0,
    },
    {
        .name = "Coconut Cove", .subtitle = "Palm trees, beach huts and a turquoise sea",
        .numPts = 23,
        .pts = { {0,0,0,22},{0,90,0,22},{15,160,1,22},{60,205,2,22},{130,215,3,22},{190,190,3,22},{215,135,2,22},{200,80,1,22},{160,50,0,22},{150,0,0,22},{175,-50,0,22},{230,-75,1,22},{280,-60,2,22},{310,-10,3,22},{345,25,3,22},{390,15,2,22},{405,-45,1,22},{385,-115,0,22},{320,-155,0,22},{240,-170,0,22},{150,-165,0,22},{70,-145,0,22},{20,-95,0,22} },
        .scenery = SCENERY_BEACH,
        .skyTop = {18,122,245,255}, .skyBottom = {165,225,255,255}, .fog = {182,228,255,255},
        .ground = {240,220,160,255}, .road = {170,160,150,255}, .rumbleA = {250,120,40,255}, .rumbleB = {250,250,250,255},
        .wallA = {250,250,250,255}, .wallB = {40,180,200,255},
        .fogDensity = 0.0030f, .grip = 0.97f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.2f,
        .numRamps = 1, .ramps = { {0.62f, 14.0f} },
        .numBoxRows = 3, .boxRows = { 0.08f, 0.30f, 0.72f },
        .scFrom = 0.363f, .scTo = 0.504f, .scSide = 1, .scIsRoad = false, .scHint = "Shortcut: a sandy track behind the beach huts - boost through the soft sand!",
        .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .groundFar = {20,150,215,255}, .farStart = 30, .farEnd = 75,
        .musicSeed = 71, .bpm = 144, .musicKey = 65, .musicScale = 2,
    },
    {
        .name = "Dusty Dunes Rally", .subtitle = "Cacti, pyramids and a blazing sun",
        .numPts = 17,
        .pts = { {0,0,0,24}, {0,120,2,24}, {-20,205,4,24}, {-85,245,3,24}, {-160,235,1,24}, {-195,180,0,24}, {-175,128,2,24}, {-118,104,4,24}, {-95,60,2,24}, {-125,10,0,24}, {-195,-5,1,24}, {-255,-35,3,24}, {-275,-105,1,24}, {-235,-165,0,24}, {-150,-175,2,24}, {-80,-145,3,24}, {-30,-90,1,24} },
        .scenery = SCENERY_DESERT,
        .skyTop = {30,110,230,255}, .skyBottom = {200,220,245,255}, .fog = {232,214,182,255},
        .ground = {242,186,96,255}, .road = {156,124,104,255}, .rumbleA = {200,60,30,255}, .rumbleB = {250,220,120,255},
        .wallA = {170,90,50,255}, .wallB = {230,200,140,255},
        .fogDensity = 0.0032f, .grip = 0.95f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.2f,
        .numRamps = 2, .ramps = { {0.22f, 14.0f}, {0.56f, 12.0f} },
        .numBoxRows = 3, .boxRows = { 0.10f, 0.40f, 0.82f },
        .scFrom = 0.266f, .scTo = 0.436f, .scSide = 1, .scIsRoad = false, .scHint = "Bumpy moguls! Shortcut: a gap after the first jump leads across the sand.",
        .numBumps = 2, .bumps = { {0.615f, 0.70f}, {0.86f, 0.95f} }, .bumpAmp = 0.75f, .bumpPeriod = 13,
        .groundFar = {240,200,130,255}, .farStart = 25, .farEnd = 140,
        .musicSeed = 23, .bpm = 138, .musicKey = 57, .musicScale = 2,
    },
    {
        .name = "Frosty Peak Pass", .subtitle = "Slippery ice and a climb through the pines",
        .numPts = 18,
        .pts = { {0,0,0,20}, {0,80,3,20}, {20,145,7,20}, {75,178,10,20}, {140,168,12,20}, {172,125,12,20}, {162,72,10,20}, {120,42,8,20}, {105,0,7,20}, {135,-42,6,20}, {195,-55,6,20}, {238,-95,5,20}, {228,-168,4,20}, {165,-208,2,20}, {82,-196,1,20}, {40,-152,0,20}, {30,-100,0,20}, {10,-60,0,20} },
        .scenery = SCENERY_SNOW,
        .skyTop = {52,112,225,255}, .skyBottom = {185,215,250,255}, .fog = {205,222,248,255},
        .ground = {235,240,250,255}, .road = {150,162,192,255}, .rumbleA = {40,90,200,255}, .rumbleB = {250,250,255,255},
        .wallA = {200,40,50,255}, .wallB = {250,250,255,255},
        .fogDensity = 0.0038f, .grip = 0.72f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.4f,
        .numRamps = 1, .ramps = { {0.72f, 12.0f} },
        .numBoxRows = 3, .boxRows = { 0.08f, 0.45f, 0.88f },
        .scFrom = 0.198f, .scTo = 0.371f, .scSide = -1, .scIsRoad = false, .scHint = "Moguls on the descent. Shortcut: snowy trail through the pines on the left.",
        .numBumps = 1, .bumps = { {0.58f, 0.66f} }, .bumpAmp = 0.55f, .bumpPeriod = 12,
        .groundFar = {215,225,245,255}, .farStart = 25, .farEnd = 140,
        .musicSeed = 37, .bpm = 132, .musicKey = 62, .musicScale = 3,
    },
    {
        .name = "Ghoulwood Manor", .subtitle = "Creaky boardwalks past a haunted castle",
        .numPts = 17,
        .pts = { {0,0,0,20},{0,100,1,20},{-15,170,3,20},{-70,205,5,20},{-135,190,7,20},{-158,135,8,20},{-125,92,8,20},{-72,72,7,20},{-58,22,6,20},{-95,-22,5,20},{-160,-28,6,20},{-215,-62,8,20},{-222,-135,9,20},{-172,-185,7,20},{-100,-195,4,20},{-40,-162,2,20},{-10,-100,1,20} },
        .scenery = SCENERY_SPOOKY,
        .skyTop = {36,20,100,255}, .skyBottom = {175,95,180,255}, .fog = {112,78,142,255},
        .ground = {100,118,82,255}, .road = {182,142,108,255}, .rumbleA = {170,80,220,255}, .rumbleB = {255,165,50,255},
        .wallA = {150,135,185,255}, .wallB = {100,90,125,255},
        .fogDensity = 0.0046f, .grip = 0.98f, .night = true, .rainbowRoad = false, .noGround = false, .wallHeight = 1.3f,
        .numRamps = 1, .ramps = { {0.62f, 12.0f} },
        .numBoxRows = 3, .boxRows = { 0.06f, 0.45f, 0.80f },
        .scFrom = 0.218f, .scTo = 0.351f, .scSide = 1, .scIsRoad = false, .scHint = "Rickety boardwalk bumps. Shortcut: cut through the graveyard on the right... if you dare.",
        .numBumps = 1, .bumps = { {0.70f, 0.78f} }, .bumpAmp = 0.45f, .bumpPeriod = 10,
        .groundFar = {88,76,112,255}, .farStart = 25, .farEnd = 120,
        .musicSeed = 83, .bpm = 128, .musicKey = 58, .musicScale = 1,
    },
    {
        .name = "Starlight Spire", .subtitle = "A rainbow ribbon above the night sky",
        .numPts = 17,
        .pts = { {0,0,0,18}, {0,140,6,18}, {-30,220,14,18}, {-110,250,20,18}, {-190,220,22,18}, {-210,150,18,18}, {-170,100,12,18}, {-100,90,10,18}, {-60,40,10,18}, {-80,-20,12,18}, {-150,-40,14,18}, {-220,-80,18,18}, {-230,-160,16,18}, {-170,-220,12,18}, {-80,-230,8,18}, {0,-190,4,18}, {30,-110,1,18} },
        .scenery = SCENERY_STARLIGHT,
        .skyTop = {5,5,25,255}, .skyBottom = {40,20,80,255}, .fog = {30,15,60,255},
        .ground = {40,20,70,255}, .road = {255,255,255,255}, .rumbleA = {255,255,255,255}, .rumbleB = {255,120,220,255},
        .wallA = {120,255,255,255}, .wallB = {255,120,255,255},
        .fogDensity = 0.0028f, .grip = 1.0f, .night = true, .rainbowRoad = true, .noGround = true, .wallHeight = 0.9f,
        .numRamps = 2, .ramps = { {0.20f, 14.0f}, {0.76f, 14.0f} },
        .numBoxRows = 3, .boxRows = { 0.10f, 0.58f, 0.88f },
        .scFrom = 0.392f, .scTo = 0.579f, .scSide = 1, .scIsRoad = true, .scHint = "Shortcut: a narrow star bridge on the right - nail the line!",
        .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .musicSeed = 59, .bpm = 156, .musicKey = 64, .musicScale = 1,
    },
    {
        .name = "Mudslide Megadome", .subtitle = "Night-time supercross under the stadium lights",
        .numPts = 180,
        .pts = { {0,-40,0.0,28}, {0,-24,0.0,28}, {0,-8,0.0,28}, {0,8,0.0,28}, {0,24,0.0,28}, {0,40,0.0,28}, {5,54,0.0,28}, {19,62,0.0,28}, {35,62,0.0,28}, {51,62,0.0,28}, {67,61,0.0,28}, {80,53,0.0,28}, {84,38,0.0,28}, {84,22,0.0,28}, {84,6,0.0,28}, {84,-10,0.0,28}, {84,-26,0.0,28}, {84,-42,0.0,28}, {84,-58,0.0,28}, {84,-74,0.0,28}, {84,-90,0.0,28}, {84,-106,0.0,28}, {84,-122,0.0,28}, {86,-138,0.0,28}, {98,-149,0.0,28}, {114,-150,0.0,28}, {130,-150,0.0,28}, {146,-150,0.0,28}, {162,-150,0.0,28}, {177,-145,0.0,28}, {186,-133,0.0,28}, {187,-117,0.0,28}, {179,-104,0.0,28}, {164,-98,0.0,28}, {149,-93,0.0,28}, {142,-79,0.0,28}, {142,-63,0.0,28}, {142,-47,0.0,28}, {142,-31,0.0,28}, {142,-15,0.0,28}, {142,1,0.0,28}, {142,17,0.0,28}, {142,33,0.0,28}, {143,49,0.0,28}, {153,61,0.0,28}, {168,64,0.0,28}, {184,64,0.0,28}, {200,64,0.0,28}, {216,64,0.0,28}, {232,64,0.0,28}, {248,64,0.0,28}, {264,64,0.0,28}, {280,64,0.0,28}, {296,64,0.0,28}, {312,64,0.0,28}, {328,64,0.0,28}, {344,64,0.0,28}, {360,64,0.0,28}, {376,64,0.0,28}, {392,64,0.0,28}, {408,64,0.0,28}, {424,62,0.0,28}, {435,50,0.0,28}, {436,34,0.0,28}, {436,18,0.0,28}, {436,2,0.0,28}, {436,-14,0.0,28}, {436,-30,0.0,28}, {436,-46,0.0,28}, {440,-61,0.0,28}, {454,-70,0.0,28}, {470,-70,0.0,28}, {486,-70,0.0,28}, {500,-63,0.0,28}, {508,-50,0.0,28}, {508,-34,0.0,28}, {508,-18,0.0,28}, {508,-2,0.0,28}, {508,14,0.0,28}, {508,30,0.0,28}, {508,46,0.0,28}, {508,62,0.0,28}, {508,78,0.0,28}, {508,94,0.0,28}, {508,110,0.0,28}, {508,126,0.0,28}, {503,142,0.0,28}, {490,151,0.0,28}, {474,152,0.0,28}, {458,152,0.0,28}, {442,152,0.0,28}, {426,152,0.0,28}, {410,152,0.0,28}, {394,152,0.0,28}, {378,152,0.0,28}, {362,152,0.0,28}, {346,152,0.0,28}, {330,152,0.0,28}, {314,152,0.0,28}, {298,152,0.0,28}, {282,152,0.0,28}, {266,152,0.0,28}, {250,152,0.0,28}, {234,152,0.0,28}, {219,151,0.8,28}, {207,141,2.6,28}, {204,125,4.7,28}, {204,109,6.4,28}, {204,93,7.0,28}, {204,77,7.0,28}, {204,61,7.0,28}, {204,45,7.0,28}, {204,29,7.0,28}, {204,13,7.0,28}, {208,-2,7.0,28}, {222,-10,7.0,28}, {238,-10,7.0,28}, {254,-10,7.0,28}, {270,-10,7.0,28}, {286,-10,7.0,28}, {302,-10,1.6,28}, {318,-10,0.0,28}, {334,-10,0.0,28}, {350,-10,0.0,28}, {365,-14,0.0,28}, {374,-27,0.0,28}, {374,-43,0.0,28}, {374,-59,0.0,28}, {374,-75,0.0,28}, {374,-91,0.0,28}, {374,-107,0.0,28}, {374,-123,0.0,28}, {374,-139,0.0,28}, {374,-155,0.0,28}, {374,-171,0.0,28}, {374,-187,0.0,28}, {374,-203,0.0,28}, {373,-219,0.0,28}, {370,-235,0.0,28}, {366,-250,0.0,28}, {360,-265,0.0,28}, {353,-279,0.0,28}, {345,-293,0.0,28}, {335,-306,0.0,28}, {324,-317,0.0,28}, {312,-328,0.0,28}, {299,-337,0.0,28}, {285,-345,0.0,28}, {270,-351,0.0,28}, {255,-356,0.0,28}, {239,-360,0.0,28}, {223,-362,0.0,28}, {207,-362,0.0,28}, {191,-361,0.0,28}, {176,-358,0.0,28}, {160,-353,0.0,28}, {145,-348,0.0,28}, {131,-340,0.0,28}, {118,-332,0.0,28}, {105,-322,0.0,28}, {94,-311,0.0,28}, {83,-298,0.0,28}, {74,-285,0.0,28}, {66,-271,0.0,28}, {60,-256,0.0,28}, {55,-241,0.0,28}, {52,-225,0.0,28}, {50,-210,0.0,28}, {50,-194,0.0,28}, {50,-178,0.0,28}, {50,-162,0.0,28}, {49,-145,0.0,28}, {40,-133,0.0,28}, {24,-130,0.0,28}, {9,-127,0.0,28}, {0,-114,0.0,28}, {0,-98,0.0,28}, {0,-82,0.0,28}, {0,-66,0.0,28}, {0,-50,0.0,28} },
        .scenery = SCENERY_STADIUM,
        .skyTop = {2,2,6,255}, .skyBottom = {8,7,14,255}, .fog = {9,8,14,255},
        .ground = {150,98,56,255}, .road = {176,122,78,255}, .rumbleA = {120,78,46,255}, .rumbleB = {142,94,56,255},
        .wallA = {235,40,45,255}, .wallB = {250,250,250,255},
        .fogDensity = 0.0022f, .grip = 0.97f, .night = true, .rainbowRoad = false, .noGround = false, .wallHeight = 1.3f,
        .numRamps = 2, .ramps = { {0.6002f, 12.0f}, {0.6590f, 12.0f} },
        .numBoxRows = 6, .boxRows = { 0.0519f, 0.2085f, 0.3684f, 0.5006f, 0.8107f, 0.9591f },
        .scFrom = 0.7864f, .scTo = 0.9045f, .scSide = -1, .scIsRoad = true, .scHint = "Shortcut: a dark gap in the dirt bank at the top of the big U-turn - cut straight across!",
        .numBumps = 5, .bumps = { {0.4223f,0.4745f}, {0.4964f,0.5702f}, {0.6433f,0.6579f}, {0.9368f,0.9521f}, {0.9779f,0.9870f} },
        .bumpAmp = 0.95f, .bumpPeriod = 11.0f,
        .groundFar = {0,0,0,0}, .farStart = 0, .farEnd = 0,
        .musicSeed = 64, .bpm = 164, .musicKey = 57, .musicScale = 3,
    },
    {
        .name = "Grand Tumble Raceway", .subtitle = "A classic GP circuit: big sweepers and the chevron tunnel",
        .numPts = 74, .pts = { {144,138,0.0,24}, {144,160,0.0,30}, {144,183,0.0,30}, {144,206,0.0,30}, {144,228,0.0,30}, {142,249,0.0,30}, {135,269,0.1,30}, {123,287,0.1,30}, {108,302,0.1,30}, {90,314,0.2,30}, {70,321,0.2,30}, {49,323,0.2,30}, {28,321,0.3,30}, {8,314,0.3,30}, {-10,302,0.4,30}, {-25,287,0.4,30}, {-37,269,0.4,30}, {-44,249,0.5,30}, {-46,228,0.5,30}, {-46,208,0.5,30}, {-46,188,0.5,30}, {-46,168,0.2,30}, {-46,148,0.0,30}, {-46,128,-3.2,30}, {-46,108,-6.5,30}, {-46,88,-6.5,30}, {-46,68,-6.5,30}, {-46,48,-6.5,30}, {-46,28,-6.5,30}, {-46,8,-6.5,30}, {-46,-12,-3.2,30}, {-46,-32,0.0,30}, {-54,-56,0.4,30}, {-74,-71,0.8,30}, {-92,-78,1.2,30}, {-112,-88,1.1,30}, {-127,-103,1.1,30}, {-139,-122,1.0,30}, {-144,-143,0.9,30}, {-144,-165,0.8,30}, {-138,-186,0.8,30}, {-127,-204,0.7,30}, {-111,-219,0.6,30}, {-93,-232,0.6,30}, {-74,-245,0.5,30}, {-56,-258,0.5,30}, {-37,-271,0.4,30}, {-19,-284,0.4,30}, {-0,-296,0.3,30}, {18,-309,0.3,30}, {37,-319,0.3,30}, {59,-324,0.2,30}, {80,-322,0.2,30}, {101,-315,0.1,30}, {119,-302,0.1,30}, {132,-285,0.1,30}, {141,-265,0.0,30}, {144,-244,0.0,30}, {144,-221,0.0,30}, {144,-199,0.0,30}, {144,-176,0.0,30}, {144,-154,0.0,30}, {144,-132,0.0,30}, {144,-109,0.0,30}, {144,-87,0.0,30}, {144,-64,0.0,30}, {144,-42,0.0,30}, {144,-19,0.0,30}, {144,3,0.0,30}, {144,26,0.0,30}, {144,48,0.0,30}, {144,71,0.0,30}, {144,93,0.0,30}, {144,116,0.0,30} },
        .numRiver = 7, .river = { {206,-196,22}, {206,-152,30}, {206,-108,30}, {206,-65,30}, {206,-21,30}, {206,22,30}, {206,66,22} },
        .scenery = SCENERY_RACEWAY,
        .skyTop = {38,108,236,255}, .skyBottom = {168,214,255,255}, .fog = {188,224,255,255},
        .ground = {112,192,72,255}, .road = {150,150,156,255}, .rumbleA = {225,40,40,255}, .rumbleB = {250,250,250,255},
        .wallA = {222,36,36,255}, .wallB = {250,250,250,255},
        .fogDensity = 0.0020f, .grip = 1.0f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.15f,
        .numRamps = 0, .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .numBoxRows = 3, .boxRows = { 0.14f, 0.52f, 0.86f },
        .scFrom = 0.050f, .scTo = 0.248f, .scSide = 1, .scIsRoad = false, .scHint = "Shortcut: slip through the gap in the checkered wall and cut the infield grass!",
        .groundFar = {80,165,70,255}, .farStart = 40, .farEnd = 160,
        .musicSeed = 311, .bpm = 152, .musicKey = 67, .musicScale = 0,
        .numZones = 4, .zones = { {0.0559f, 0.2414f, ZN_CHECKER}, {0.3163f, 0.3785f, ZN_TUNNEL|ZN_BOOSTFLOOR}, {0.4478f, 1.0000f, ZN_CHECKER}, {0.7627f, 1.0000f, ZN_LOWWALL_L} },
        .hazard = HZ_NONE, .wallStyle = WS_RACEWAY, .musicStyle = MUS_FANFARE, .shoulderW = 8.0f, .followTerrain = true, .waterLevel = -1.3f,
    },
    {
        .name = "Canopy River Parkway", .subtitle = "Golden-hour jungle: a gorge jump, a rope bridge and coconut monkeys",
        .numPts = 88, .pts = { {-32,-136,0.0,24}, {-32,-116,0.0,22}, {-32,-96,0.0,22}, {-32,-71,0.3,22}, {-32,-46,0.6,22}, {-33,-26,0.5,22}, {-38,-6,0.4,22}, {-45,13,0.3,22}, {-54,31,0.1,22}, {-62,49,0.0,22}, {-70,72,0.2,22}, {-75,96,0.4,22}, {-76,116,0.6,22}, {-78,136,0.8,22}, {-82,157,0.7,22}, {-89,176,0.7,22}, {-99,195,0.6,22}, {-113,211,0.5,22}, {-134,232,0.4,22}, {-147,248,0.5,22}, {-155,268,0.5,22}, {-157,288,0.6,23}, {-155,309,0.7,23}, {-147,328,0.7,23}, {-134,345,0.8,23}, {-117,358,0.9,24}, {-98,366,0.9,24}, {-77,368,1.0,24}, {-55,368,1.0,23}, {-32,368,1.0,22}, {-9,368,1.0,22}, {13,368,1.0,21}, {36,368,1.0,20}, {54,368,2.1,20}, {72,368,3.2,20}, {104,368,1.8,20}, {134,368,0.6,22}, {151,361,0.4,22}, {158,344,0.3,22}, {158,321,0.3,22}, {158,298,0.3,22}, {158,275,0.3,22}, {158,252,0.3,22}, {158,229,0.3,22}, {158,206,0.3,22}, {158,183,0.3,22}, {156,157,0.3,22}, {151,131,0.4,22}, {146,110,0.4,22}, {140,89,0.3,22}, {134,68,0.3,22}, {129,46,0.2,22}, {123,25,0.2,22}, {118,5,0.2,22}, {116,-16,0.2,22}, {116,-37,0.3,22}, {118,-58,0.3,22}, {123,-78,0.3,22}, {129,-100,0.3,22}, {134,-121,0.3,22}, {140,-142,0.3,22}, {146,-163,0.3,22}, {151,-185,0.3,22}, {156,-210,0.3,22}, {158,-236,0.3,22}, {158,-258,0.3,22}, {158,-279,0.3,22}, {158,-301,0.3,22}, {158,-322,0.3,22}, {158,-344,0.3,22}, {151,-361,0.4,22}, {134,-368,0.6,22}, {130,-368,1.4,16}, {111,-368,1.5,16}, {93,-368,1.5,16}, {74,-368,1.6,16}, {54,-368,1.5,18}, {34,-368,1.4,20}, {13,-362,3.9,19}, {-2,-347,6.5,19}, {-8,-326,9.0,18}, {-8,-296,9.5,18}, {-11,-273,5.5,20}, {-20,-251,1.5,22}, {-29,-229,0.8,22}, {-32,-206,0.0,22}, {-32,-183,0.0,22}, {-32,-159,0.0,22} },
        .numRiver = 15, .river = { {88,788,15}, {88,428,14}, {88,368,13}, {118,327,12}, {118,243,12}, {117,164,12}, {99,90,12}, {78,5,12}, {85,-92,12}, {106,-172,12}, {118,-243,12}, {118,-326,12}, {102,-368,12}, {102,-428,13}, {102,-788,15} },
        .scenery = SCENERY_JUNGLE,
        .skyTop = {246,142,62,255}, .skyBottom = {226,240,165,255}, .fog = {236,214,150,255},
        .ground = {74,146,52,255}, .road = {158,112,70,255}, .rumbleA = {120,82,44,255}, .rumbleB = {214,186,120,255},
        .wallA = {112,76,44,255}, .wallB = {94,62,36,255},
        .fogDensity = 0.0034f, .grip = 0.96f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.0f,
        .numRamps = 0, .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .numBoxRows = 4, .boxRows = { 0.10f, 0.32f, 0.56f, 0.95f },
        .scFrom = 0.195f, .scTo = 0.306f, .scSide = -1, .scIsRoad = false, .scHint = "Shortcut: a jungle trail cuts inside the big left sweeper - mind the monkeys!",
        .groundFar = {40,110,45,255}, .farStart = 30, .farEnd = 120,
        .musicSeed = 523, .bpm = 132, .musicKey = 62, .musicScale = 3,
        .numZones = 6, .zones = { {0.3608f, 0.3795f, ZN_BOOSTFLOOR}, {0.3795f, 0.3961f, ZN_GAP}, {0.4311f, 0.7932f, ZN_OPEN_L|ZN_HAZARD}, {0.8148f, 0.8438f, ZN_PLANKS}, {0.8646f, 0.9145f, ZN_CAVE}, {0.0000f, 0.2000f, ZN_HAZARD} },
        .hazard = HZ_MONKEYS, .wallStyle = WS_LOG, .musicStyle = MUS_JUNGLE, .shoulderW = 6.0f, .followTerrain = true, .waterLevel = -1.4f,
    },
    {
        .name = "Shellby Shores", .subtitle = "Tides, crabs and a ramp-hop over the lagoon",
        .numPts = 87, .pts = { {335,-118,0.0,24}, {335,-98,-0.1,24}, {335,-78,-0.2,24}, {335,-55,-0.3,24}, {335,-31,-0.4,24}, {335,-8,-0.6,24}, {335,15,-0.7,24}, {335,39,-0.8,24}, {335,62,-0.9,24}, {335,92,-0.2,24}, {332,113,-0.0,24}, {322,132,0.1,24}, {308,148,0.3,24}, {289,158,0.4,24}, {272,164,1.2,24}, {255,170,2.0,24}, {227,180,1.6,24}, {207,188,1.8,24}, {187,195,2.0,24}, {167,202,2.2,24}, {139,213,3.2,24}, {109,223,1.4,24}, {80,234,0.8,24}, {58,238,1.0,24}, {35,236,1.3,24}, {13,228,1.5,24}, {-6,217,1.6,24}, {-25,206,1.6,24}, {-44,195,1.7,24}, {-63,184,1.7,24}, {-82,173,1.8,24}, {-101,162,1.9,24}, {-120,151,1.9,24}, {-139,140,2.0,24}, {-158,129,2.0,24}, {-177,118,2.1,24}, {-196,107,2.1,24}, {-215,96,2.2,24}, {-234,85,2.3,24}, {-253,75,2.3,24}, {-272,64,2.4,24}, {-291,53,2.4,24}, {-309,42,2.5,24}, {-326,26,2.6,24}, {-335,6,2.8,24}, {-334,-17,2.9,24}, {-323,-37,3.0,24}, {-310,-52,3.0,24}, {-298,-67,3.0,24}, {-285,-83,3.0,24}, {-284,-84,3.0,24}, {-273,-101,2.5,24}, {-267,-121,2.0,24}, {-263,-141,1.7,24}, {-260,-160,1.3,24}, {-256,-180,1.0,24}, {-248,-203,0.9,24}, {-232,-222,0.8,24}, {-211,-234,0.7,24}, {-187,-238,0.6,24}, {-165,-238,0.6,24}, {-143,-238,0.6,24}, {-121,-238,0.5,24}, {-99,-238,0.5,24}, {-77,-238,0.5,24}, {-55,-238,0.5,24}, {-33,-238,0.5,24}, {-11,-238,0.4,24}, {11,-238,0.4,24}, {33,-238,0.4,24}, {55,-238,0.4,24}, {77,-238,0.4,24}, {99,-238,0.4,24}, {121,-238,0.3,24}, {143,-238,0.3,24}, {165,-238,0.3,24}, {187,-238,0.3,24}, {209,-238,0.3,24}, {231,-238,0.2,24}, {253,-238,0.2,24}, {275,-238,0.2,24}, {298,-233,0.1,24}, {317,-220,0.0,24}, {330,-201,-0.1,24}, {335,-178,-0.2,24}, {335,-158,-0.2,24}, {335,-138,-0.2,24} },
        .numRiver = 5, .river = { {231,147,9}, {292,316,13}, {0,0,0}, {113,190,9}, {175,359,13} },
        .scenery = SCENERY_ISLAND,
        .skyTop = {28,128,246,255}, .skyBottom = {170,230,255,255}, .fog = {186,230,255,255},
        .ground = {242,222,166,255}, .road = {226,204,156,255}, .rumbleA = {250,250,250,255}, .rumbleB = {232,112,62,255},
        .wallA = {250,250,250,255}, .wallB = {232,112,62,255},
        .fogDensity = 0.0024f, .grip = 0.97f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.0f,
        .numRamps = 0, .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .numBoxRows = 3, .boxRows = { 0.12f, 0.40f, 0.76f },
        .scFrom = 0.476f, .scTo = 0.590f, .scSide = 1, .scIsRoad = true, .scHint = "Shortcut: take the little ramp into the cave in the cliff wall!",
        .groundFar = {30,150,220,255}, .farStart = 40, .farEnd = 90,
        .musicSeed = 619, .bpm = 118, .musicKey = 65, .musicScale = 0,
        .numZones = 7, .zones = { {0.0120f, 0.0950f, ZN_TIDE|ZN_OPEN_L}, {0.1531f, 0.1718f, ZN_BOOSTFLOOR}, {0.1718f, 0.1873f, ZN_GAP}, {0.2205f, 0.2361f, ZN_BOOSTFLOOR}, {0.2361f, 0.2527f, ZN_GAP}, {0.2700f, 0.4500f, ZN_HAZARD}, {0.7000f, 0.9200f, ZN_HAZARD} },
        .hazard = HZ_CRABS, .tideAmp = 0.55f, .tidePeriod = 14.0f, .wallStyle = WS_NONE, .musicStyle = MUS_CALYPSO, .shoulderW = 9.0f, .followTerrain = true, .waterLevel = -1.2f,
    },
    {
        .name = "Clover Creek Farm", .subtitle = "Dusty lanes, mooing cows and moles that pop up underfoot",
        .numPts = 59, .pts = { {-95,59,0.0,24}, {-95,83,0.0,28}, {-95,107,0.0,28}, {-95,131,0.0,28}, {-95,155,0.0,28}, {-95,179,0.0,28}, {-93,200,0.0,28}, {-86,220,0.1,28}, {-74,238,0.1,28}, {-59,253,0.1,28}, {-41,264,0.2,28}, {-21,271,0.2,28}, {-0,274,0.2,28}, {21,271,0.3,28}, {41,264,0.3,28}, {59,253,0.4,28}, {74,238,0.4,28}, {85,220,0.4,28}, {92,200,0.5,28}, {94,179,0.5,28}, {94,159,0.5,28}, {94,139,0.5,28}, {94,116,1.7,28}, {94,92,2.8,28}, {94,69,4.0,28}, {94,46,2.8,28}, {94,22,1.7,28}, {94,-1,0.5,28}, {94,-21,0.3,28}, {94,-41,0.2,28}, {94,-61,0.0,28}, {92,-87,0.0,28}, {83,-112,0.0,28}, {75,-130,0.0,28}, {66,-148,0.0,28}, {58,-173,0.0,28}, {55,-199,0.0,28}, {52,-220,0.0,28}, {43,-239,0.0,28}, {29,-255,0.0,28}, {11,-267,0.0,28}, {-9,-273,0.0,28}, {-31,-273,0.0,28}, {-51,-267,0.0,28}, {-69,-255,0.0,28}, {-83,-239,0.0,28}, {-92,-220,0.0,28}, {-95,-199,0.0,28}, {-95,-177,0.0,28}, {-95,-156,0.0,28}, {-95,-134,0.0,28}, {-95,-113,0.0,28}, {-95,-91,0.0,28}, {-95,-70,0.0,28}, {-95,-48,0.0,28}, {-95,-27,0.0,28}, {-95,-5,0.0,28}, {-95,16,0.0,28}, {-95,38,0.0,28} },
        .scenery = SCENERY_FARM,
        .skyTop = {78,148,236,255}, .skyBottom = {255,226,172,255}, .fog = {246,226,190,255},
        .ground = {98,178,62,255}, .road = {164,118,72,255}, .rumbleA = {236,226,200,255}, .rumbleB = {140,96,56,255},
        .wallA = {244,238,224,255}, .wallB = {214,204,186,255},
        .fogDensity = 0.0022f, .grip = 0.98f, .night = false, .rainbowRoad = false, .noGround = false, .wallHeight = 1.0f,
        .numRamps = 0, .numBumps = 0, .bumpAmp = 0, .bumpPeriod = 12,
        .numBoxRows = 3, .boxRows = { 0.08f, 0.40f, 0.70f },
        .scFrom = 0.612f, .scTo = 0.812f, .scSide = -1, .scIsRoad = false, .scHint = "Shortcut: through the open gate and across the hay field!",
        .groundFar = {120,170,70,255}, .farStart = 40, .farEnd = 150,
        .musicSeed = 733, .bpm = 140, .musicKey = 67, .musicScale = 2,
        .numZones = 2, .zones = { {0.4613f, 0.5600f, ZN_HAZARD}, {0.8011f, 0.9200f, ZN_HAZARD} },
        .hazard = HZ_MOLES, .wallStyle = WS_FENCE, .musicStyle = MUS_COUNTRY, .shoulderW = 7.0f, .followTerrain = true, .waterLevel = -2.0f,
    },
};

/* Cups: the four v7 courses lead off the Sprout Cup like a classic first cup; the Grand Tour runs all eleven. */
const CupDef CUPS[NUM_CUPS] = {
    { "Sprout Cup",  "Easy-going circuits for warming up",   4, { 7, 10, 9, 1 },   {  96, 200,  80, 255 } },
    { "Blossom Cup", "Hills, dunes, ice and a haunted manor", 4, { 0, 2, 3, 4 },    { 240, 130, 180, 255 } },
    { "Thunder Cup", "Gorges, supercross and the rainbow finale", 3, { 8, 6, 5 },       { 250, 196,  40, 255 } },
    { "Grand Tour",  "All eleven courses back to back",       11, { 7, 10, 9, 1, 0, 2, 3, 4, 8, 6, 5 }, { 120, 150, 255, 255 } },
};
int GpTrackCount(void) { return (G.gpCup < 0 || G.gpCup >= NUM_CUPS) ? NUM_TRACKS : CUPS[G.gpCup].n; }
int GpTrack(int race)
{
    if (G.gpCup < 0 || G.gpCup >= NUM_CUPS) return race % NUM_TRACKS;
    return CUPS[G.gpCup].tracks[race % CUPS[G.gpCup].n];
}

/* deterministic RNG for scenery */
static unsigned int trng = 1;
static float TR(float lo, float hi) { trng = trng*1664525u + 1013904223u; return lo + (hi - lo)*((trng >> 8)/16777216.0f); }

static void CatmullRom(const float *p0, const float *p1, const float *p2, const float *p3, float t, float *out)
{
    float t2 = t*t, t3 = t2*t;
    for (int i = 0; i < 4; i++) {
        out[i] = 0.5f*((2*p1[i]) + (-p0[i] + p2[i])*t + (2*p0[i] - 5*p1[i] + 4*p2[i] - p3[i])*t2 +
                       (-p0[i] + 3*p1[i] - 3*p2[i] + p3[i])*t3);
    }
}

/* dense spline evaluation -> arrays of (x,z,h,w) */
static int SplineDense(const TrackDef *d, float (*out)[4], int perSeg)
{
    int c = 0;
    for (int i = 0; i < d->numPts; i++) {
        const float *p0 = d->pts[(i - 1 + d->numPts) % d->numPts];
        const float *p1 = d->pts[i];
        const float *p2 = d->pts[(i + 1) % d->numPts];
        const float *p3 = d->pts[(i + 2) % d->numPts];
        for (int j = 0; j < perSeg; j++) CatmullRom(p0, p1, p2, p3, (float)j/perSeg, out[c++]);
    }
    return c;
}

void TrackOutline(int index, Vector2 *out, int maxPts, int *count)
{
    static float dense[MAX_CTRL_PTS*16][4];
    const TrackDef *d = &TRACK_DEFS[index];
    int n = SplineDense(d, dense, 16);
    int step = (n + maxPts - 1)/maxPts; if (step < 1) step = 1;
    int c = 0;
    for (int i = 0; i < n && c < maxPts; i += step) out[c++] = (Vector2){ dense[i][0], dense[i][1] };
    *count = c;
}

int TrackWrap(const Track *tr, int i) { i %= tr->n; if (i < 0) i += tr->n; return i; }

float TrackHalfWidth(const Track *tr, int seg) { return tr->s[TrackWrap(tr, seg)].width*0.5f; }

float TrackWallLimit(const Track *tr, int seg, float lat)
{
    const TrackSample *s = &tr->s[TrackWrap(tr, seg)];
    if ((lat < 0 && (s->zone & ZN_OPEN_L)) || (lat > 0 && (s->zone & ZN_OPEN_R))) return s->edge[lat > 0 ? 1 : 0] + 40.0f;
    return s->edge[lat > 0 ? 1 : 0] - 0.9f;
}

/* Road height, except over a gorge gap (nothing to land on) and beside open sections, where the
   bank slopes down to the river / sea and the kart follows the terrain. */
float TrackSurfaceY(const Track *tr, int seg, float lat, Vector3 p, float roadY)
{
    const TrackSample *s = &tr->s[TrackWrap(tr, seg)];
    if (!s->zone) return roadY;
    if (s->zone & ZN_GAP) return -60.0f;
    float hw = s->width*0.5f + 1.2f;
    if (((lat < 0 && (s->zone & ZN_OPEN_L)) || (lat > 0 && (s->zone & ZN_OPEN_R))) && fabsf(lat) > hw) {
        float t = TerrainY(tr, p.x, p.z) + 0.45f;
        return fminf(roadY, Lerp(roadY, t, Clamp((fabsf(lat) - hw)/2.0f, 0, 1)));
    }
    return roadY;
}

Vector3 TrackPoint(const Track *tr, int seg, float lat)
{
    const TrackSample *s = &tr->s[TrackWrap(tr, seg)];
    return Vector3Add(s->pos, Vector3Scale(s->right, lat));
}

void TrackLocate(const Track *tr, Vector3 p, int hint, int *seg, float *lat, float *along, float *groundY)
{
    int best = 0; float bd = 1e30f;
    int from = 0, to = tr->n - 1;
    if (hint >= 0) { from = hint - 14; to = hint + 14; }
    for (int i = from; i <= to; i++) {
        int k = TrackWrap(tr, i);
        float dx = p.x - tr->s[k].pos.x, dz = p.z - tr->s[k].pos.z;
        float dy = p.y - tr->s[k].pos.y;
        float d = dx*dx + dz*dz + dy*dy*0.25f;
        if (d < bd) { bd = d; best = k; }
    }
    const TrackSample *s = &tr->s[best];
    float t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/tr->spacing;
    if (t < 0) { best = TrackWrap(tr, best - 1); s = &tr->s[best]; t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/tr->spacing; }
    t = Clamp(t, 0.0f, 1.0f);
    const TrackSample *s2 = &tr->s[TrackWrap(tr, best + 1)];
    Vector3 r = Vector3Normalize(Vector3Lerp(s->right, s2->right, t));
    Vector3 c = Vector3Lerp(s->pos, s2->pos, t);
    *seg = best;
    *along = t;
    *lat = (p.x - c.x)*r.x + (p.z - c.z)*r.z;
    *groundY = c.y;
}

/* ------------------------------------------------------------------ */
/* Shortcut corridor                                                    */
/* ------------------------------------------------------------------ */
bool TrackShortcutLocate(const Track *tr, Vector3 p, int *idx, float *lat, float *along, float *groundY)
{
    *idx = 0; *lat = 1e6f; *along = 0; *groundY = p.y;
    if (tr->scN < 2) return false;
    int best = 0; float bd = 1e30f;
    for (int i = 0; i < tr->scN; i++) {
        float dx = p.x - tr->sc[i].pos.x, dz = p.z - tr->sc[i].pos.z;
        float d = dx*dx + dz*dz;
        if (d < bd) { bd = d; best = i; }
    }
    if (best > tr->scN - 2) best = tr->scN - 2;
    float sp = tr->sc[1].dist - tr->sc[0].dist;
    const TrackSample *s = &tr->sc[best];
    float t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/sp;
    if (t < 0 && best > 0) { best--; s = &tr->sc[best]; t = ((p.x - s->pos.x)*s->fwd.x + (p.z - s->pos.z)*s->fwd.z)/sp; }
    bool inside = true;
    if (best == 0 && t < 0) inside = false;
    if (best == tr->scN - 2 && t > 1) inside = false;
    float tc = Clamp(t, 0.0f, 1.0f);
    const TrackSample *s2 = &tr->sc[best + 1];
    Vector3 c = Vector3Lerp(s->pos, s2->pos, tc);
    *idx = best; *along = tc;
    *lat = (p.x - c.x)*s->right.x + (p.z - c.z)*s->right.z;
    *groundY = c.y;
    if (fabsf(*lat) > tr->scHalf) inside = false;
    if (fabsf(p.y - c.y) > 6.0f) inside = false;
    return inside;
}

/* progress-equivalent main-track sample for a position on the shortcut */
int TrackShortcutMainSeg(const Track *tr, int idx, float along)
{
    int span = TrackWrap(tr, tr->scB - tr->scA);
    float f = (idx + along)/(float)(tr->scN - 1);
    return TrackWrap(tr, tr->scA + (int)(span*Clamp(f, 0, 1) + 0.5f));
}

static bool InMainCorridor(const Track *tr, Vector3 p, float margin)
{
    int seg; float lat, al, gy;
    TrackLocate(tr, p, -1, &seg, &lat, &al, &gy);
    return fabsf(lat) <= tr->s[seg].edge[lat > 0 ? 1 : 0] + margin && fabsf(p.y - gy) < 6.0f;
}

static bool InShortcut(const Track *tr, Vector3 p, float margin)
{
    if (tr->scN < 2) return false;
    int i; float lat, al, gy;
    Track *mt = (Track *)tr;
    float h = mt->scHalf; mt->scHalf = h + margin;
    bool r = TrackShortcutLocate(tr, p, &i, &lat, &al, &gy);
    mt->scHalf = h;
    return r;
}

static void BuildShortcut(Track *tr)
{
    const TrackDef *d = tr->def;
    tr->scN = 0;
    if (d->scTo <= d->scFrom) return;
    int n = tr->n;
    tr->scA = (int)(d->scFrom*n) % n;
    tr->scB = (int)(d->scTo*n) % n;
    tr->scHalf = d->scIsRoad ? 4.0f : 5.0f;
    const TrackSample *a = &tr->s[tr->scA], *b = &tr->s[tr->scB];
    float side = (float)d->scSide;
    Vector3 A = Vector3Add(a->pos, Vector3Scale(a->right, side*a->width*0.5f*0.45f));
    Vector3 B = Vector3Add(b->pos, Vector3Scale(b->right, side*b->width*0.5f*0.45f));
    float len = Vector3Distance((Vector3){ A.x, 0, A.z }, (Vector3){ B.x, 0, B.z });
    int cnt = (int)(len/2.0f) + 1;
    if (cnt > 256) cnt = 256;
    if (cnt < 4) return;
    /* cubic Bezier leaving tangent to the road and rejoining tangent to it */
    float L = len*0.33f;
    Vector3 P1 = Vector3Add(A, Vector3Scale(a->fwd, L)), P2 = Vector3Subtract(B, Vector3Scale(b->fwd, L));
    static Vector3 tmp[2048];
    int m = 2000;
    float arc = 0;
    for (int i = 0; i <= m; i++) {
        float u = (float)i/m, iu = 1 - u;
        Vector3 q = Vector3Add(Vector3Add(Vector3Scale(A, iu*iu*iu), Vector3Scale(P1, 3*iu*iu*u)), Vector3Add(Vector3Scale(P2, 3*iu*u*u), Vector3Scale(B, u*u*u)));
        tmp[i] = q;
        if (i) arc += Vector3Distance((Vector3){ q.x, 0, q.z }, (Vector3){ tmp[i - 1].x, 0, tmp[i - 1].z });
    }
    cnt = (int)(arc/2.0f) + 1;
    if (cnt > 256) cnt = 256;
    float acc = 0; int j = 0;
    for (int i = 0; i < cnt; i++) {
        float target = arc*i/(cnt - 1);
        while (j < m && acc + Vector3Distance((Vector3){ tmp[j].x, 0, tmp[j].z }, (Vector3){ tmp[j + 1].x, 0, tmp[j + 1].z }) < target) {
            acc += Vector3Distance((Vector3){ tmp[j].x, 0, tmp[j].z }, (Vector3){ tmp[j + 1].x, 0, tmp[j + 1].z }); j++;
        }
        TrackSample *s = &tr->sc[i];
        s->pos = tmp[j];
        s->pos.y = Lerp(A.y, B.y, (float)i/(cnt - 1)) + sinf((float)i/(cnt - 1)*PI)*0.35f;
        s->dist = target;
        s->curv = 0; s->ramp = false; s->bump = false;
        if (d->scenery == SCENERY_ISLAND) {     /* a little kicker ramp hops you into the cave */
            float u = (float)i/(cnt - 1);
            if (u > 0.08f && u < 0.16f) { s->pos.y += (u - 0.08f)/0.08f*1.5f; s->ramp = true; }
        }
        s->width = tr->scHalf*2;
        s->edge[0] = s->edge[1] = tr->scHalf;
    }
    for (int i = 0; i < cnt; i++) {
        Vector3 p0 = tr->sc[i > 0 ? i - 1 : 0].pos, p1 = tr->sc[i < cnt - 1 ? i + 1 : cnt - 1].pos;
        Vector3 f = Vector3Normalize((Vector3){ p1.x - p0.x, 0, p1.z - p0.z });
        tr->sc[i].fwd = f;
        tr->sc[i].right = (Vector3){ -f.z, 0, f.x };
    }
    /* sanity: the trail must stay clear of the rest of the course */
    float worst = 1e9f;
    for (int i = cnt/6; i < cnt - cnt/6; i++) for (int k = 0; k < n; k += 2) {
        int dA = TrackWrap(tr, k - tr->scA), dB = TrackWrap(tr, tr->scB - k);
        if (dA < TrackWrap(tr, tr->scB - tr->scA) + 10 && dB < TrackWrap(tr, tr->scB - tr->scA) + 10) continue; /* the skipped arc */
        float dx = tr->sc[i].pos.x - tr->s[k].pos.x, dz = tr->sc[i].pos.z - tr->s[k].pos.z;
        float cl = sqrtf(dx*dx + dz*dz) - fmaxf(tr->s[k].edge[0], tr->s[k].edge[1]) - tr->scHalf;
        if (cl < worst) worst = cl;
    }
    TraceLog(worst < 1.0f ? LOG_WARNING : LOG_INFO, "TRACK: shortcut %d samples, %.0f long (skips %.0f), clearance %.1f", cnt, arc,
             TrackWrap(tr, tr->scB - tr->scA)*tr->spacing, worst);
    tr->scN = cnt;
}

/* ------------------------------------------------------------------ */
/* Terrain: flat near the road, rolling hills / dunes / mountains / sea  */
/* further out. Stored as a height grid so props sit on the surface.     */
/* ------------------------------------------------------------------ */
#define TGMAX 200
static int TG = 112;                  /* grid resolution (finer for the stadium's trench banks) */
static float TH[TGMAX + 1][TGMAX + 1];
static float tX0, tZ0, tX1, tZ1;
static int numLakes;
static Vector3 lakes[4];

float TerrainY(const Track *tr, float x, float z)
{
    if (tr->def->noGround) return tr->groundY;
    float fx = (x - tX0)/(tX1 - tX0)*TG, fz = (z - tZ0)/(tZ1 - tZ0)*TG;
    fx = Clamp(fx, 0, TG - 0.001f); fz = Clamp(fz, 0, TG - 0.001f);
    int ix = (int)fx, iz = (int)fz;
    float u = fx - ix, v = fz - iz;
    float h00 = TH[ix][iz], h10 = TH[ix + 1][iz], h11 = TH[ix + 1][iz + 1], h01 = TH[ix][iz + 1];
    /* same diagonal split as the mesh */
    if (u >= v) return h00 + u*(h10 - h00) + v*(h11 - h10);
    return h00 + v*(h01 - h00) + u*(h11 - h01);
}

static float SmoothStep(float a, float b, float x) { float t = Clamp((x - a)/(b - a), 0, 1); return t*t*(3 - 2*t); }

static float TrackDist(const Track *tr, float x, float z)
{
    float best = 1e18f;
    for (int i = 0; i < tr->n; i += 2) {
        float dx = x - tr->s[i].pos.x, dz = z - tr->s[i].pos.z, dd = dx*dx + dz*dz;
        if (dd < best) best = dd;
    }
    for (int i = 0; i < tr->scN; i += 2) {
        float dx = x - tr->sc[i].pos.x, dz = z - tr->sc[i].pos.z, dd = dx*dx + dz*dz;
        if (dd < best) best = dd;
    }
    return sqrtf(best);
}

static float TerrainRaw(const Track *tr, float x, float z, float dist)
{
    const TrackDef *d = tr->def;
    unsigned int sd = 900u + (unsigned)tr->index*13u;
    float f = SmoothStep(30, 105, dist);
    float h = 0;
    switch (d->scenery) {
    case SCENERY_MEADOW: h = f*(WorldNoise(x/75.0f, z/75.0f, sd)*30.0f - 5.0f) + SmoothStep(160, 420, dist)*25.0f; break;
    case SCENERY_DESERT: h = f*(WorldNoise(x/55.0f, z/55.0f, sd)*15.0f + 3.0f*sinf(x*0.045f + z*0.02f)); break;
    case SCENERY_SNOW:   h = f*(WorldNoise(x/70.0f, z/70.0f, sd)*32.0f) + SmoothStep(90, 340, dist)*75.0f; break;
    case SCENERY_SPOOKY: h = f*(WorldNoise(x/45.0f, z/45.0f, sd)*13.0f); break;
    case SCENERY_BEACH:  h = -5.5f*SmoothStep(d->farStart + 4, d->farEnd + 10, dist) + f*(WorldNoise(x/40.0f, z/40.0f, sd) - 0.5f)*2.0f; break;
    default: break;
    }
    for (int l = 0; l < numLakes; l++) {
        float ld = sqrtf((x - lakes[l].x)*(x - lakes[l].x) + (z - lakes[l].z)*(z - lakes[l].z))/lakes[l].y;
        if (ld < 1.0f) h = Lerp(-3.2f, h, SmoothStep(0.5f, 1.0f, ld));
    }
    return tr->groundY + h;
}

/* Stadium floor: a flat dirt infield at plateau height with the course cut into it as a trench
   (sloped banks rising STADIUM_RISE over STADIUM_BANK_W), plus earth ramps under the raised sections.
   Overpass samples are skipped so the lower road keeps its trench under the bridge. */
static float StadiumH(const Track *tr, float x, float z)
{
    const float plateau = STADIUM_RISE - 0.3f;
    float carve = 1e9f, emb = -1e9f;
    for (int i = 0; i < tr->n; i++) {
        const TrackSample *a = &tr->s[i];
        if (a->bridge) continue;
        float dx = x - a->pos.x, dz = z - a->pos.z;
        if (fabsf(dx) > 40 || fabsf(dz) > 40) continue;
        float dd = dx*dx + dz*dz, hw = a->width*0.5f + 1.0f, y = a->pos.y;
        float lim = hw + STADIUM_BANK_W;
        if (dd < lim*lim) {
            float t = fmaxf(0, sqrtf(dd) - hw)/STADIUM_BANK_W;
            float c = y - 0.3f + STADIUM_RISE*t*t*(3 - 2*t);
            if (c < carve) carve = c;
        }
        if (y > 0.6f) {
            float e = sqrtf(dd) - hw;
            float v = y - 0.3f - fmaxf(0, e)*0.9f;
            if (v > emb) emb = v;
        }
    }
    for (int i = 0; i < tr->scN; i++) {
        float dx = x - tr->sc[i].pos.x, dz = z - tr->sc[i].pos.z;
        if (fabsf(dx) > 30 || fabsf(dz) > 30) continue;
        float hw = tr->scHalf + 0.8f, lim = hw + STADIUM_BANK_W*0.7f;
        float dd = dx*dx + dz*dz;
        if (dd < lim*lim) {
            float t = fmaxf(0, sqrtf(dd) - hw)/(STADIUM_BANK_W*0.7f);
            float c = tr->sc[i].pos.y - 0.3f + STADIUM_RISE*t*t*(3 - 2*t);
            if (c < carve) carve = c;
        }
    }
    return fminf(fmaxf(plateau, emb), carve);
}

/* v7 courses: the landscape follows the road (cuttings, embankments, a hill over the tunnel),
   with river channels / a lake / the sea carved in afterwards. */
static bool InsideLoop(const Track *tr, float x, float z)
{
    bool in = false;
    for (int i = 0, j = tr->n - 2; i < tr->n; j = i, i += 2) {
        Vector3 a = tr->s[i].pos, b = tr->s[j].pos;
        if ((a.z > z) != (b.z > z) && x < (b.x - a.x)*(z - a.z)/(b.z - a.z) + a.x) in = !in;
    }
    return in;
}

static float SegDist2D(float px, float pz, float ax, float az, float bx, float bz, float *t)
{
    float vx = bx - ax, vz = bz - az, l2 = vx*vx + vz*vz;
    float u = l2 > 0 ? Clamp(((px - ax)*vx + (pz - az)*vz)/l2, 0, 1) : 0;
    *t = u;
    float dx = px - (ax + vx*u), dz = pz - (az + vz*u);
    return sqrtf(dx*dx + dz*dz);
}

/* distance to the nearest river / lake / channel polyline, as a fraction of its half-width (<1 = in the water) */
static float RiverFrac(const TrackDef *d, float x, float z)
{
    float best = 99.0f;
    for (int i = 0; i + 1 < d->numRiver; i++) {
        const float *a = d->river[i], *b = d->river[i + 1];
        if (a[2] <= 0 || b[2] <= 0) continue;          /* polyline break */
        float t, dd = SegDist2D(x, z, a[0], a[1], b[0], b[1], &t);
        float hw = Lerp(a[2], b[2], t);
        if (dd/hw < best) best = dd/hw;
    }
    return best;
}

static float FollowBase(const Track *tr, float x, float z, float dist)
{
    const TrackDef *d = tr->def;
    unsigned int sd = 900u + (unsigned)tr->index*13u;
    switch (d->scenery) {
    case SCENERY_RACEWAY: return SmoothStep(45, 150, dist)*(WorldNoise(x/85.0f, z/85.0f, sd)*26.0f - 3.0f) + SmoothStep(180, 420, dist)*30.0f;
    case SCENERY_JUNGLE:  return SmoothStep(30, 110, dist)*(WorldNoise(x/55.0f, z/55.0f, sd)*20.0f) + SmoothStep(120, 400, dist)*85.0f;
    case SCENERY_ISLAND:
        if (InsideLoop(tr, x, z)) return 0.3f + SmoothStep(30, 110, dist)*WorldNoise(x/50.0f, z/50.0f, sd)*9.0f;
        return 0.3f - 7.5f*SmoothStep(12, 55, dist);
    case SCENERY_FARM:    return SmoothStep(45, 160, dist)*(WorldNoise(x/95.0f, z/95.0f, sd)*12.0f) + SmoothStep(220, 420, dist)*28.0f;
    default: return 0;
    }
}

static unsigned char scCover[MAX_TRACK_SAMPLES];
static float FollowH(const Track *tr, float x, float z, float dist)
{
    const TrackDef *d = tr->def;
    float base = FollowBase(tr, x, z, dist);
    float carve = 1e9f, emb = -1e9f, cover = -1e9f;
    for (int i = 0; i < tr->n; i++) {
        const TrackSample *a = &tr->s[i];
        if (a->zone & ZN_GAP) continue;
        float dx = x - a->pos.x, dz = z - a->pos.z;
        if (fabsf(dx) > 70 || fabsf(dz) > 70) continue;
        float hw = fmaxf(a->edge[0], a->edge[1]) + 0.8f;
        float e = sqrtf(dx*dx + dz*dz) - hw;
        if (e > 70) continue;
        if (a->zone & (ZN_TUNNEL | ZN_CAVE)) {        /* a hill over the bore */
            float v = a->pos.y + 6.4f - fmaxf(0, e)*0.5f;
            if (v > emb) emb = v;
            if (e < 1.5f && a->pos.y + 6.4f > cover) cover = a->pos.y + 6.4f;
            continue;
        }
        float y = a->pos.y - 0.45f;
        float c = y + fmaxf(0, e)*0.75f;
        if (c < carve) carve = c;
        float v = y - fmaxf(0, e)*0.7f;
        if (v > emb) emb = v;
    }
    for (int i = 0; i < tr->scN; i++) {
        float dx = x - tr->sc[i].pos.x, dz = z - tr->sc[i].pos.z;
        if (fabsf(dx) > 50 || fabsf(dz) > 50) continue;
        float e = sqrtf(dx*dx + dz*dz) - (tr->scHalf + 1.0f);
        float y = tr->sc[i].pos.y - 0.45f;
        if (d->scenery == SCENERY_ISLAND) {           /* the cliff over the cave */
            if (!scCover[i]) continue;
            float v = tr->sc[i].pos.y + 7.5f - fmaxf(0, e)*0.6f; if (v > emb) emb = v;
            if (e < 1.0f && tr->sc[i].pos.y + 7.5f > cover) cover = tr->sc[i].pos.y + 7.5f;
            continue;
        }
        float c = y + fmaxf(0, e)*0.75f; if (c < carve) carve = c;
        float v = y - fmaxf(0, e)*0.7f; if (v > emb) emb = v;
    }
    float h = fmaxf(fminf(fmaxf(base, emb), carve), cover);
    if (d->numRiver > 0) {
        float rf = RiverFrac(d, x, z);
        if (rf < 1.8f) {
            float bed = d->waterLevel - 2.6f;
            h = fminf(h, Lerp(bed, h, SmoothStep(0.5f, 1.6f, rf)));
        }
    }
    return h;
}

static void BuildTerrain(Track *tr)
{
    const TrackDef *d = tr->def;
    if (d->scenery == SCENERY_STADIUM) {
        TG = 192;
        tX0 = tr->mapMin.x - STADIUM_MARGIN - 8; tX1 = tr->mapMax.x + STADIUM_MARGIN + 8;
        tZ0 = tr->mapMin.y - STADIUM_MARGIN - 8; tZ1 = tr->mapMax.y + STADIUM_MARGIN + 8;
        numLakes = 0;
        for (int gx = 0; gx <= TG; gx++) for (int gz = 0; gz <= TG; gz++) {
            float x = tX0 + (tX1 - tX0)*gx/TG, z = tZ0 + (tZ1 - tZ0)*gz/TG;
            TH[gx][gz] = StadiumH(tr, x, z);
        }
        tr->hasWater = false;
        tr->waterY = -100.0f;
        return;
    }
    if (d->followTerrain) {
        TG = 192;
        tX0 = tr->mapMin.x - 420; tX1 = tr->mapMax.x + 420; tZ0 = tr->mapMin.y - 420; tZ1 = tr->mapMax.y + 420;
        numLakes = 0;
        for (int i = 0; i < tr->scN; i++) scCover[i] = !InMainCorridor(tr, tr->sc[i].pos, 4.0f);
        for (int gx = 0; gx <= TG; gx++) for (int gz = 0; gz <= TG; gz++) {
            float x = tX0 + (tX1 - tX0)*gx/TG, z = tZ0 + (tZ1 - tZ0)*gz/TG;
            TH[gx][gz] = FollowH(tr, x, z, TrackDist(tr, x, z));
        }
        tr->hasWater = d->numRiver > 0 || d->scenery == SCENERY_ISLAND;
        tr->waterY = tr->waterBase = d->waterLevel;
        tr->tideOffset = 0;
        return;
    }
    TG = 112;
    tX0 = tr->mapMin.x - 420; tX1 = tr->mapMax.x + 420; tZ0 = tr->mapMin.y - 420; tZ1 = tr->mapMax.y + 420;
    numLakes = 0;
    unsigned int save = trng;
    trng = 4242u + (unsigned)tr->index*101u;
    int want = d->scenery == SCENERY_MEADOW ? 2 : d->scenery == SCENERY_DESERT ? 1 : 0;
    for (int tries = 0; tries < 200 && numLakes < want; tries++) {
        int i = (int)TR(0, (float)tr->n - 1);
        float side = TR(0, 1) < 0.5f ? -1.0f : 1.0f;
        float R = d->scenery == SCENERY_DESERT ? 15.0f : TR(22, 32);
        Vector3 c = Vector3Add(tr->s[i].pos, Vector3Scale(tr->s[i].right, side*(tr->s[i].width*0.5f + 18 + R)));
        if (TrackDist(tr, c.x, c.z) < R + 16) continue;
        lakes[numLakes++] = (Vector3){ c.x, R, c.z };
    }
    trng = save;
    for (int gx = 0; gx <= TG; gx++) for (int gz = 0; gz <= TG; gz++) {
        float x = tX0 + (tX1 - tX0)*gx/TG, z = tZ0 + (tZ1 - tZ0)*gz/TG;
        TH[gx][gz] = d->noGround ? tr->groundY : TerrainRaw(tr, x, z, TrackDist(tr, x, z));
    }
    tr->hasWater = d->scenery == SCENERY_BEACH || numLakes > 0;
    tr->waterY = tr->groundY - 0.9f;
}

/* ------------------------------------------------------------------ */
/* Sky dome (gradient, sun / moon, stars), soft clouds, painted panorama */
/* ------------------------------------------------------------------ */
static void BuildSky(Track *tr, MeshBuilder *mb)
{
    const TrackDef *d = tr->def;
    trng = 777u + (unsigned)tr->index*31u;
    float R = 600.0f;
    bool enh = G.settings.visualMode == 1;
    int slices = enh ? 48 : 32, rings = enh ? 20 : 12;
    Vector3 far = { 0, -5000, 0 };
    Vector2 uv = { 0.5f, 0.5f };
    for (int i = 0; i < rings; i++) {
        float a0 = (PI*0.5f)*i/rings, a1 = (PI*0.5f)*(i + 1)/rings;
        Color c0 = ColorMix(d->skyBottom, d->skyTop, powf((float)i/rings, 0.6f));
        Color c1 = ColorMix(d->skyBottom, d->skyTop, powf((float)(i + 1)/rings, 0.6f));
        float h0 = 1.0f - (float)i/rings, h1 = 1.0f - (float)(i + 1)/rings;
        Color haze = d->night ? ColorScale(d->skyBottom, 1.2f) : ColorMix(d->skyBottom, WHITE, 0.4f);
        float hk = enh ? 0.8f : 0.55f;
        c0 = ColorMix(ColorScale(c0, enh ? 1.08f : 1.04f), haze, powf(h0, 5.0f)*hk);
        c1 = ColorMix(ColorScale(c1, enh ? 1.08f : 1.04f), haze, powf(h1, 5.0f)*hk);
        for (int j = 0; j < slices; j++) {
            float b0 = 2*PI*j/slices, b1 = 2*PI*(j + 1)/slices;
            Vector3 p00 = { R*cosf(a0)*cosf(b0), R*sinf(a0), R*cosf(a0)*sinf(b0) };
            Vector3 p01 = { R*cosf(a0)*cosf(b1), R*sinf(a0), R*cosf(a0)*sinf(b1) };
            Vector3 p10 = { R*cosf(a1)*cosf(b0), R*sinf(a1), R*cosf(a1)*sinf(b0) };
            Vector3 p11 = { R*cosf(a1)*cosf(b1), R*sinf(a1), R*cosf(a1)*sinf(b1) };
            MB_TriUV(mb, p00, p01, p11, uv, uv, uv, c0, c0, c1, far, false);
            MB_TriUV(mb, p00, p11, p10, uv, uv, uv, c0, c1, c1, far, false);
        }
    }
    for (int j = 0; j < slices; j++) {
        float b0 = 2*PI*j/slices, b1 = 2*PI*(j + 1)/slices;
        Vector3 a = { R*cosf(b0), 0, R*sinf(b0) }, b = { R*cosf(b1), 0, R*sinf(b1) };
        Vector3 a2 = { a.x, -R*0.5f, a.z }, b2 = { b.x, -R*0.5f, b.z };
        Color bc = d->noGround ? ColorScale(d->fog, 0.5f) : d->fog;
        MB_TriUV(mb, a, b, b2, uv, uv, uv, d->fog, d->fog, bc, far, false);
        MB_TriUV(mb, a, b2, a2, uv, uv, uv, d->fog, bc, bc, far, false);
    }
    if (d->scenery == SCENERY_STADIUM) return;      /* indoors: a pitch-black roof, no stars or moon */
    if (d->night) {
        for (int i = 0; i < 500; i++) {
            float th = TR(0, 2*PI), ph = TR(0.08f, 1.5f);
            Vector3 c = { R*0.95f*cosf(ph)*cosf(th), R*0.95f*sinf(ph), R*0.95f*cosf(ph)*sinf(th) };
            float s = TR(0.8f, 2.6f);
            Color sc = ColorFromHSV(TR(180, 300), TR(0, 0.4f), 1.0f);
            Vector3 up = { 0, s, 0 }, rt = { -sinf(th)*s, 0, cosf(th)*s };
            MB_TriUV(mb, Vector3Add(c, up), Vector3Add(c, rt), Vector3Subtract(c, up), uv, uv, uv, sc, sc, sc, Vector3Scale(c, 2), false);
            MB_TriUV(mb, Vector3Add(c, up), Vector3Subtract(c, rt), Vector3Subtract(c, up), uv, uv, uv, sc, sc, sc, Vector3Scale(c, 2), false);
        }
    }
    /* sun or moon disc with a soft halo */
    Vector3 mc = d->night ? (Vector3){ -300, 330, -330 } : Vector3Scale(Vector3Normalize((Vector3){ -0.55f, 0.32f, -0.77f }), 560.0f);
    Vector3 r1 = Vector3Normalize(Vector3CrossProduct(mc, (Vector3){ 0, 1, 0 }));
    Vector3 u1 = Vector3Normalize(Vector3CrossProduct(r1, mc));
    Color core = d->night ? (Color){ 255, 250, 220, 255 } : (Color){ 255, 252, 225, 255 };
    Color halo = d->night ? ColorMix(d->skyTop, core, 0.25f) : ColorMix(d->skyBottom, core, 0.55f);
    float rc = d->night ? 28 : 24, rh = d->night ? 60 : 75;
    for (int j = 0; j < 24; j++) {
        float a0 = 2*PI*j/24, a1 = 2*PI*(j + 1)/24;
        Vector3 p0 = Vector3Add(mc, Vector3Add(Vector3Scale(r1, cosf(a0)*rc), Vector3Scale(u1, sinf(a0)*rc)));
        Vector3 p1 = Vector3Add(mc, Vector3Add(Vector3Scale(r1, cosf(a1)*rc), Vector3Scale(u1, sinf(a1)*rc)));
        Vector3 q0 = Vector3Add(mc, Vector3Add(Vector3Scale(r1, cosf(a0)*rh), Vector3Scale(u1, sinf(a0)*rh)));
        Vector3 q1 = Vector3Add(mc, Vector3Add(Vector3Scale(r1, cosf(a1)*rh), Vector3Scale(u1, sinf(a1)*rh)));
        Color hz = halo; hz.a = 0;
        Color hi = halo; hi.a = 150;
        MB_TriUV(mb, p0, q0, q1, uv, uv, uv, hi, hz, hz, Vector3Scale(mc, 2), false);
        MB_TriUV(mb, p0, q1, p1, uv, uv, uv, hi, hz, hi, Vector3Scale(mc, 2), false);
        MB_TriUV(mb, mc, p0, p1, uv, uv, uv, core, core, core, Vector3Scale(mc, 2), false);
    }
}

static void BuildClouds(Track *tr, MeshBuilder *mb)
{
    const TrackDef *d = tr->def;
    if (d->scenery == SCENERY_STARLIGHT || d->scenery == SCENERY_STADIUM) return;
    trng = 999u + (unsigned)tr->index*17u;
    Color cc = d->night ? (Color){ 150, 120, 190, 200 } : WHITE;
    int n = d->night ? 10 : 22;
    for (int i = 0; i < n; i++) {
        float th = TR(0, 2*PI), h = TR(70, 210), r = TR(420, 500), w = TR(90, 170);
        Vector3 c = { r*cosf(th), h, r*sinf(th) };
        Vector3 rt = { -sinf(th)*w*0.5f, 0, cosf(th)*w*0.5f }, up = { 0, w*0.25f, 0 };
        Color bot = ColorMix(cc, d->skyBottom, 0.3f); bot.a = cc.a;
        MB_TriUV(mb, Vector3Subtract(Vector3Subtract(c, rt), up), Vector3Subtract(Vector3Add(c, rt), up), Vector3Add(Vector3Add(c, rt), up),
                 (Vector2){ 0, 1 }, (Vector2){ 1, 1 }, (Vector2){ 1, 0 }, bot, bot, cc, (Vector3){ 0, 0, 0 }, false);
        MB_TriUV(mb, Vector3Subtract(Vector3Subtract(c, rt), up), Vector3Add(Vector3Add(c, rt), up), Vector3Add(Vector3Subtract(c, rt), up),
                 (Vector2){ 0, 1 }, (Vector2){ 1, 0 }, (Vector2){ 0, 0 }, bot, cc, cc, (Vector3){ 0, 0, 0 }, false);
    }
}

static void BuildPano(Track *tr, MeshBuilder *mb)
{
    float R = 540.0f, y0 = -32.0f, y1 = 132.0f;
    int seg = 64;
    if (tr->def->scenery == SCENERY_STADIUM) return;   /* the stands are real geometry */
    for (int j = 0; j < seg; j++) {
        float b0 = 2*PI*j/seg, b1 = 2*PI*(j + 1)/seg;
        Vector3 a = { R*cosf(b0), y0, R*sinf(b0) }, b = { R*cosf(b1), y0, R*sinf(b1) };
        Vector3 at = { a.x, y1, a.z }, bt = { b.x, y1, b.z };
        float u0 = 2.0f*j/seg, u1 = 2.0f*(j + 1)/seg;
        MB_TriUV(mb, a, b, bt, (Vector2){ u0, 1 }, (Vector2){ u1, 1 }, (Vector2){ u1, 0 }, WHITE, WHITE, WHITE, (Vector3){ 0, 0, 0 }, false);
        MB_TriUV(mb, a, bt, at, (Vector2){ u0, 1 }, (Vector2){ u1, 0 }, (Vector2){ u0, 0 }, WHITE, WHITE, WHITE, (Vector3){ 0, 0, 0 }, false);
    }
    (void)tr;
}

/* Red/white striped concrete barriers wherever the course is raised above the infield (ramps,
   embankments, the overpass), the overpass deck slab, and its pillars. Trench sections have none:
   the dirt banks are the walls there. */
static void ArenaQuad(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Rectangle r, float uA, float uB, Color c, Vector3 outRef)
{
    float u0 = r.x + r.width*uA, u1 = r.x + r.width*uB;
    MB_QuadUV(mb, p0, p1, p2, p3, (Vector2){ u0, r.y + r.height }, (Vector2){ u1, r.y + r.height },
              (Vector2){ u1, r.y }, (Vector2){ u0, r.y }, c, outRef, true);
}

static void ArenaBox(MeshBuilder *mb, Vector3 lo, Vector3 hi, Rectangle r, Color c)
{
    Vector3 ctr = Vector3Scale(Vector3Add(lo, hi), 0.5f);
    Vector3 p[8];
    for (int i = 0; i < 8; i++) p[i] = (Vector3){ (i & 1) ? hi.x : lo.x, (i & 2) ? hi.y : lo.y, (i & 4) ? hi.z : lo.z };
    ArenaQuad(mb, p[0], p[1], p[3], p[2], r, 0, 1, c, ctr);
    ArenaQuad(mb, p[5], p[4], p[6], p[7], r, 0, 1, c, ctr);
    ArenaQuad(mb, p[4], p[0], p[2], p[6], r, 0, 1, c, ctr);
    ArenaQuad(mb, p[1], p[5], p[7], p[3], r, 0, 1, c, ctr);
    ArenaQuad(mb, p[2], p[3], p[7], p[6], r, 0, 1, c, ctr);
}

static void BuildStadiumBarriers(Track *tr, MeshBuilder *wb)
{
    int n = tr->n;
    Rectangle stripes = ArenaUV(ARENA_STRIPES), conc = ArenaUV(ARENA_CONCRETE);
    const float bh = 1.1f, bw = 0.5f, slab = 1.4f;
    bool *need = MemAlloc(sizeof(bool)*n*2);
    for (int i = 0; i < n; i++) {
        const TrackSample *a = &tr->s[i];
        for (int sd = 0; sd < 2; sd++) {
            float side = sd ? 1.0f : -1.0f;
            Vector3 o = Vector3Add(a->pos, Vector3Scale(a->right, side*(a->edge[sd] + 1.2f)));
            need[i*2 + sd] = a->bridge || a->ramp || a->pos.y - TerrainY(tr, o.x, o.z) > 0.8f;
        }
    }
    /* widen the runs a little so barriers start before the drop-off is visible */
    bool *grow = MemAlloc(sizeof(bool)*n*2);
    for (int i = 0; i < n; i++) for (int sd = 0; sd < 2; sd++) {
        bool v = false;
        for (int k = -3; k <= 3 && !v; k++) v = need[((i + k + n) % n)*2 + sd];
        grow[i*2 + sd] = v;
    }
    for (int i = 0; i < n; i++) {
        int j = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[j];
        for (int sd = 0; sd < 2; sd++) {
            if (!grow[i*2 + sd] || !grow[j*2 + sd]) continue;
            float side = sd ? 1.0f : -1.0f;
            Vector3 ia = Vector3Add(a->pos, Vector3Scale(a->right, side*a->edge[sd]));
            Vector3 ib = Vector3Add(b->pos, Vector3Scale(b->right, side*b->edge[sd]));
            if (InShortcut(tr, ia, 0.6f) || InShortcut(tr, ib, 0.6f)) continue;
            Vector3 oa = Vector3Add(ia, Vector3Scale(a->right, side*bw));
            Vector3 ob = Vector3Add(ib, Vector3Scale(b->right, side*bw));
            float ga = a->bridge ? a->pos.y - slab : fminf(TerrainY(tr, oa.x, oa.z), a->pos.y) - 0.2f;
            float gbb = b->bridge ? b->pos.y - slab : fminf(TerrainY(tr, ob.x, ob.z), b->pos.y) - 0.2f;
            float ua = (i & 1) ? 0.5f : 0.0f, ub = ua + 0.5f;
            Vector3 ta = { ia.x, ia.y + bh, ia.z }, tb = { ib.x, ib.y + bh, ib.z };
            Vector3 toa = { oa.x, oa.y + bh, oa.z }, tob = { ob.x, ob.y + bh, ob.z };
            Vector3 inRef = Vector3Add(a->pos, Vector3Scale(a->right, side*(a->edge[sd] + 5.0f)));
            ArenaQuad(wb, ia, ib, tb, ta, stripes, ua, ub, WHITE, inRef);                 /* road face */
            ArenaQuad(wb, ta, tb, tob, toa, conc, 0, 1, WHITE, (Vector3){ a->pos.x, a->pos.y - 50, a->pos.z });
            Vector3 la = { oa.x, ga, oa.z }, lb = { ob.x, gbb, ob.z };
            Vector3 outRef = Vector3Add(a->pos, Vector3Scale(a->right, side*(a->edge[sd] - 5.0f)));
            ArenaQuad(wb, la, lb, tob, toa, stripes, ua, ua + 0.5f*1.0f, ColorScale(WHITE, 0.85f), outRef); /* outer face */
            /* end caps where a run starts/stops */
            int pi = (i + n - 1) % n;
            if (!grow[pi*2 + sd]) ArenaQuad(wb, ia, oa, toa, ta, conc, 0, 1, WHITE, Vector3Add(ia, Vector3Scale(a->fwd, 3)));
            if (!grow[((j + 1) % n)*2 + sd]) ArenaQuad(wb, ib, ob, tob, tb, conc, 0, 1, WHITE, Vector3Subtract(ib, Vector3Scale(b->fwd, 3)));
        }
        /* overpass deck: slab underside */
        if (a->bridge && b->bridge) {
            Vector3 la = Vector3Add(a->pos, Vector3Scale(a->right, -(a->edge[0] + bw))), ra = Vector3Add(a->pos, Vector3Scale(a->right, a->edge[1] + bw));
            Vector3 lb = Vector3Add(b->pos, Vector3Scale(b->right, -(b->edge[0] + bw))), rb = Vector3Add(b->pos, Vector3Scale(b->right, b->edge[1] + bw));
            la.y -= slab; ra.y -= slab; lb.y -= slab; rb.y -= slab;
            ArenaQuad(wb, la, ra, rb, lb, conc, 0, 1, ColorScale(WHITE, 0.6f), (Vector3){ a->pos.x, a->pos.y + 50, a->pos.z });
        }
    }
    /* pillars under the deck, kept off the lower road */
    for (int i = 0; i < n; i += 5) {
        const TrackSample *a = &tr->s[i];
        if (!a->bridge) continue;
        for (int sd = -1; sd <= 1; sd += 2) {
            Vector3 c = Vector3Add(a->pos, Vector3Scale(a->right, sd*(a->edge[sd > 0] - 0.6f)));
            bool clear = true;
            for (int k = 0; k < n && clear; k += 2) {
                if (tr->s[k].bridge || tr->s[k].pos.y > a->pos.y - 3) continue;
                float dx = c.x - tr->s[k].pos.x, dz = c.z - tr->s[k].pos.z, lim = fmaxf(tr->s[k].edge[0], tr->s[k].edge[1]) + 1.6f;
                if (dx*dx + dz*dz < lim*lim) clear = false;
            }
            if (!clear) continue;
            float g = TerrainY(tr, c.x, c.z) - 0.3f;
            ArenaBox(wb, (Vector3){ c.x - 0.7f, g, c.z - 0.7f }, (Vector3){ c.x + 0.7f, a->pos.y - slab, c.z + 0.7f }, conc, ColorScale(WHITE, 0.8f));
        }
    }
    MemFree(grow);
    MemFree(need);
}

/* ------------------------------------------------------------------ */
/* v7 structures: chevron floors, tunnel / cave bores, plank bridge,    */
/* footbridge, overpass, rock arch, gorge lips, island cave             */
/* ------------------------------------------------------------------ */
static Vector3 SP(const TrackSample *a, float lat, float up) { return (Vector3){ a->pos.x + a->right.x*lat, a->pos.y + up, a->pos.z + a->right.z*lat }; }

/* oriented box: local x along ax (horizontal unit), y up, z = ax x up */
static void OBox(MeshBuilder *mb, Vector3 c, Vector3 ax, float hx, float hy, float hz, Color col)
{
    Vector3 az = { -ax.z, 0, ax.x };
    Vector3 p[8];
    for (int i = 0; i < 8; i++) {
        float x = (i & 1) ? hx : -hx, y = (i & 2) ? hy : -hy, z = (i & 4) ? hz : -hz;
        p[i] = (Vector3){ c.x + ax.x*x + az.x*z, c.y + y, c.z + ax.z*x + az.z*z };
    }
    Vector2 u0 = { 0, 0 }, u1 = { 1, 0 }, u2 = { 1, 1 }, u3 = { 0, 1 };
    MB_QuadUV(mb, p[0], p[1], p[3], p[2], u0, u1, u2, u3, col, c, true);
    MB_QuadUV(mb, p[4], p[5], p[7], p[6], u0, u1, u2, u3, col, c, true);
    MB_QuadUV(mb, p[0], p[4], p[6], p[2], u0, u1, u2, u3, col, c, true);
    MB_QuadUV(mb, p[1], p[5], p[7], p[3], u0, u1, u2, u3, col, c, true);
    MB_QuadUV(mb, p[2], p[3], p[7], p[6], u0, u1, u2, u3, col, c, true);
    MB_QuadUV(mb, p[0], p[1], p[5], p[4], u0, u1, u2, u3, col, c, true);
}

static void DQ(MeshBuilder *mb, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, float u0, float u1, float v0, float v1, Color c, Vector3 outRef)
{
    MB_QuadUV(mb, p0, p1, p2, p3, (Vector2){ u0, v0 }, (Vector2){ u1, v0 }, (Vector2){ u1, v1 }, (Vector2){ u0, v1 }, c, outRef, true);
}

/* a facade across the road at sample a with an opening (lat -ow..ow, 0..oh), extent W wide and H tall */
static void Portal(MeshBuilder *mb, const TrackSample *a, float ow, float oh, float W, float H, float drop, float facing, Color c)
{
    Vector3 out = Vector3Add(a->pos, Vector3Scale(a->fwd, -facing*30.0f));
    out.y += oh*0.5f;
    Vector3 L0 = SP(a, -W, -drop), L1 = SP(a, -ow, -drop), L2 = SP(a, -ow, H), L3 = SP(a, -W, H);
    DQ(mb, L0, L1, L2, L3, 0, (W - ow)/4, 0, (H + drop)/4, c, out);
    Vector3 R0 = SP(a, ow, -drop), R1 = SP(a, W, -drop), R2 = SP(a, W, H), R3 = SP(a, ow, H);
    DQ(mb, R0, R1, R2, R3, 0, (W - ow)/4, 0, (H + drop)/4, c, out);
    Vector3 T0 = SP(a, -ow, oh), T1 = SP(a, ow, oh), T2 = SP(a, ow, H), T3 = SP(a, -ow, H);
    DQ(mb, T0, T1, T2, T3, 0, 2*ow/4, 0, (H - oh)/4, c, out);
    /* ledge on top */
    Vector3 lc = Vector3Add(SP(a, 0, H + 0.3f), Vector3Scale(a->fwd, -facing*0.4f));
    OBox(mb, lc, a->right, W, 0.35f, 0.9f, ColorScale(c, 0.85f));
}

static void BuildDeco(Track *tr)
{
    const TrackDef *d = tr->def;
    tr->hasDeco = false;
    if (!d->numZones) return;
    int n = tr->n;
    MeshBuilder db[5];
    for (int k = 0; k < 5; k++) MB_Init(&db[k]);
    Color concrete = { 188, 188, 192, 255 }, darkCon = { 96, 96, 102, 255 };
    Color rock = d->scenery == SCENERY_ISLAND ? (Color){ 196, 170, 140, 255 } : (Color){ 150, 132, 112, 255 };
    for (int i = 0; i < n; i++) {
        int i1 = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[i1];
        float ha = a->width*0.5f, hb = b->width*0.5f;
        float da = a->dist, dbb = (i1 == 0 ? tr->length : b->dist);
        Vector3 below = Vector3Add(a->pos, (Vector3){ 0, -50, 0 });
        unsigned short za = a->zone, zb = b->zone;
        if ((za | zb) & ZN_GAP) {
            /* lip faces: ramp end (concrete) and landing front (rock) */
            if (!(za & ZN_GAP) && (zb & ZN_GAP))
                DQ(&db[4], SP(a, -ha - 1, -12), SP(a, ha + 1, -12), SP(a, ha + 1, 0.02f), SP(a, -ha - 1, 0.02f), 0, 1, 0, 1, darkCon, a->pos.y > -50 ? Vector3Add(a->pos, Vector3Scale(a->fwd, -20)) : below);
            if ((za & ZN_GAP) && !(zb & ZN_GAP))
                DQ(&db[3], SP(b, -hb - 6, -12), SP(b, hb + 6, -12), SP(b, hb + 6, 0.0f), SP(b, -hb - 6, 0.0f), 0, 4, 0, 3, rock, Vector3Add(b->pos, Vector3Scale(b->fwd, 20)));
            continue;
        }
        if ((za & ZN_BOOSTFLOOR) || (zb & ZN_BOOSTFLOOR)) {
            float va = da/(a->width*0.5f), vb = dbb/(a->width*0.5f);
            DQ(&db[0], SP(a, -ha, 0.02f), SP(a, ha, 0.02f), SP(b, hb, 0.02f), SP(b, -hb, 0.02f), 0, 1, va, vb, WHITE, below);
            if (!(za & ZN_TUNNEL)) {      /* raised concrete ramp sides */
                for (int sd = -1; sd <= 1; sd += 2) {
                    Vector3 e0 = SP(a, sd*(ha + 1.0f), 0.05f), e1 = SP(b, sd*(hb + 1.0f), 0.05f);
                    Vector3 g0 = e0, g1 = e1; g0.y = fminf(TerrainY(tr, e0.x, e0.z), e0.y) - 2.0f; g1.y = fminf(TerrainY(tr, e1.x, e1.z), e1.y) - 2.0f;
                    DQ(&db[4], e0, e1, g1, g0, 0, 1, 0, 1, ((i/2) & 1) ? (Color){ 255, 205, 30, 255 } : (Color){ 200, 40, 36, 255 }, a->pos);
                    Vector3 t0 = SP(a, sd*(ha + 1.0f), 0.6f), t1 = SP(b, sd*(hb + 1.0f), 0.6f);
                    DQ(&db[4], e0, e1, t1, t0, 0, 1, 0, 1, concrete, Vector3Add(a->pos, Vector3Scale(a->right, -sd*30.0f)));
                }
            }
        }
        if ((za & ZN_PLANKS) || (zb & ZN_PLANKS)) {
            float w = ha + 0.6f, wb = hb + 0.6f;
            DQ(&db[1], SP(a, -w, 0.0f), SP(a, w, 0.0f), SP(b, wb, 0.0f), SP(b, -wb, 0.0f), 0, 1, da/4.0f, dbb/4.0f, WHITE, below);
            DQ(&db[1], SP(a, -w, -0.45f), SP(a, w, -0.45f), SP(b, wb, -0.45f), SP(b, -wb, -0.45f), 0, 1, da/4.0f, dbb/4.0f, (Color){ 120, 90, 60, 255 }, Vector3Add(a->pos, (Vector3){ 0, 50, 0 }));
            for (int sd = -1; sd <= 1; sd += 2) {
                DQ(&db[1], SP(a, sd*w, 0.0f), SP(b, sd*wb, 0.0f), SP(b, sd*wb, -0.45f), SP(a, sd*w, -0.45f), 0, 1, 0, 0.1f, (Color){ 150, 110, 70, 255 }, a->pos);
                if ((i % 4) == 0) {
                    float ph = ((za & ZN_PLANKS) && !(tr->s[(i + n - 4) % n].zone & ZN_PLANKS)) || !(tr->s[(i + 4) % n].zone & ZN_PLANKS) ? 4.5f : 1.5f;
                    OBox(&db[1], SP(a, sd*(w + 0.1f), ph*0.5f - 0.4f), a->right, 0.18f, ph*0.5f + 0.4f, 0.18f, (Color){ 110, 76, 46, 255 });
                }
                /* sagging rope rails */
                float sagA = 0.25f*sinf(PI*fmodf((float)i, 4.0f)/4.0f), sagB = 0.25f*sinf(PI*fmodf((float)i + 1, 4.0f)/4.0f);
                for (int r = 0; r < 2; r++) {
                    float hh = r ? 1.35f : 0.7f;
                    Vector3 r0 = SP(a, sd*(w + 0.1f), hh - sagA), r1 = SP(b, sd*(wb + 0.1f), hh - sagB);
                    DQ(&db[4], r0, r1, (Vector3){ r1.x, r1.y + 0.09f, r1.z }, (Vector3){ r0.x, r0.y + 0.09f, r0.z }, 0, 1, 0, 1, (Color){ 214, 182, 120, 255 }, Vector3Add(a->pos, Vector3Scale(a->right, -sd*30.0f)));
                    DQ(&db[4], r0, r1, (Vector3){ r1.x, r1.y + 0.09f, r1.z }, (Vector3){ r0.x, r0.y + 0.09f, r0.z }, 0, 1, 0, 1, (Color){ 190, 160, 104, 255 }, Vector3Add(a->pos, Vector3Scale(a->right, sd*30.0f)));
                }
            }
        }
        if (za & ZN_TUNNEL) {            /* grey brick bore with a lit ceiling */
            float w = ha + 1.0f, wb = hb + 1.0f, H = 5.5f;
            for (int sd = -1; sd <= 1; sd += 2)
                DQ(&db[2], SP(a, sd*w, -0.1f), SP(b, sd*wb, -0.1f), SP(b, sd*wb, H), SP(a, sd*w, H), da/4.0f, dbb/4.0f, H/4.0f, 0, (Color){ 200, 200, 206, 255 }, Vector3Add(a->pos, Vector3Scale(a->right, sd*40.0f)));
            DQ(&db[4], SP(a, -w, H), SP(a, w, H), SP(b, wb, H), SP(b, -wb, H), 0, 1, 0, 1, darkCon, Vector3Add(a->pos, (Vector3){ 0, 50, 0 }));
            if ((i % 5) == 0) {
                Vector3 c0 = SP(a, -1.2f, H - 0.05f), c1 = SP(a, 1.2f, H - 0.05f), c2 = SP(b, 1.2f, H - 0.05f), c3 = SP(b, -1.2f, H - 0.05f);
                MB_QuadUV(&db[4], c0, c1, c2, c3, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, (Color){ 255, 236, 170, 255 }, Vector3Add(a->pos, (Vector3){ 0, 50, 0 }), false);
            }
            if (!(tr->s[(i + n - 1) % n].zone & ZN_TUNNEL)) Portal(&db[4], a, w, H, w + 16, H + 4.5f, 4.0f, 1.0f, concrete);
            if (!(zb & ZN_TUNNEL)) Portal(&db[4], b, wb, H, wb + 16, H + 4.5f, 4.0f, -1.0f, concrete);
        }
        if (za & ZN_CAVE) {              /* rough rock tube */
            float j0 = 0.6f*sinf(i*0.7f) + 0.4f*sinf(i*1.9f), j1 = 0.6f*sinf((i + 1)*0.7f) + 0.4f*sinf((i + 1)*1.9f);
            float w = ha + 1.0f + j0, wb = hb + 1.0f + j1, H0 = 6.0f + j0, H1 = 6.0f + j1;
            Color cc = { 120, 106, 92, 255 };
            for (int sd = -1; sd <= 1; sd += 2) {
                DQ(&db[3], SP(a, sd*w, -0.2f), SP(b, sd*wb, -0.2f), SP(b, sd*(wb - 1.5f), H1 - 1.0f), SP(a, sd*(w - 1.5f), H0 - 1.0f), da/5.0f, dbb/5.0f, 0, 1, cc, Vector3Add(a->pos, Vector3Scale(a->right, sd*40.0f)));
                DQ(&db[3], SP(a, sd*(w - 1.5f), H0 - 1.0f), SP(b, sd*(wb - 1.5f), H1 - 1.0f), SP(b, sd*wb*0.4f, H1), SP(a, sd*w*0.4f, H0), da/5.0f, dbb/5.0f, 1, 1.6f, ColorScale(cc, 0.8f), Vector3Add(a->pos, (Vector3){ sd*a->right.x*40, 60, sd*a->right.z*40 }));
            }
            DQ(&db[3], SP(a, -w*0.4f, H0), SP(a, w*0.4f, H0), SP(b, wb*0.4f, H1), SP(b, -wb*0.4f, H1), 0, 1, da/5.0f, dbb/5.0f, ColorScale(cc, 0.7f), Vector3Add(a->pos, (Vector3){ 0, 60, 0 }));
            if (!(tr->s[(i + n - 1) % n].zone & ZN_CAVE)) Portal(&db[3], a, w, H0 - 0.5f, w + 22, H0 + 7, 6.0f, 1.0f, rock);
            if (!(zb & ZN_CAVE)) Portal(&db[3], b, wb, H1 - 0.5f, wb + 22, H1 + 7, 6.0f, -1.0f, rock);
        }
    }
    /* course landmarks built over the road */
    if (d->scenery == SCENERY_RACEWAY) {        /* grey concrete overpass across the back straight */
        const TrackSample *a = &tr->s[(int)(0.2663f*n)];
        float span = fmaxf(a->edge[0], a->edge[1]) + 16.0f, H = 7.5f;
        OBox(&db[4], SP(a, 0, H), a->right, span, 0.7f, 4.0f, concrete);
        for (int sd = -1; sd <= 1; sd += 2) {
            OBox(&db[4], SP(a, sd*span*0.999f, H + 1.3f), a->fwd, 4.0f, 0.6f, 0.25f, darkCon);   /* end caps */
            Vector3 pc = SP(a, sd*(fmaxf(a->edge[0], a->edge[1]) + 3.0f), 0);
            float ty = TerrainY(tr, pc.x, pc.z);
            pc.y = (ty + a->pos.y + H)*0.5f;
            OBox(&db[4], pc, a->right, 1.4f, (a->pos.y + H - ty)*0.5f, 2.6f, ColorScale(concrete, 0.92f));
        }
        for (int sd = -1; sd <= 1; sd += 2) {   /* parapets */
            Vector3 c = Vector3Add(SP(a, 0, H + 1.2f), Vector3Scale(a->fwd, sd*3.8f));
            OBox(&db[4], c, a->right, span, 0.5f, 0.2f, ColorScale(concrete, 1.05f));
        }
        /* overhead start gantry */
        const TrackSample *g = &tr->s[2];
        float gw = fmaxf(g->edge[0], g->edge[1]) + 1.5f;
        for (int sd = -1; sd <= 1; sd += 2) OBox(&db[4], SP(g, sd*gw, 4.5f), g->right, 0.5f, 4.5f, 0.5f, (Color){ 220, 220, 228, 255 });
        OBox(&db[4], SP(g, 0, 9.2f), g->right, gw + 0.5f, 0.9f, 0.6f, (Color){ 40, 40, 48, 255 });
        for (int k = -3; k <= 3; k++) OBox(&db[4], Vector3Add(SP(g, k*2.2f, 9.2f), Vector3Scale(g->fwd, -0.65f)), g->right, 0.45f, 0.45f, 0.08f, (k & 1) ? (Color){ 255, 60, 50, 255 } : (Color){ 80, 255, 90, 255 });
    }
    if (d->scenery == SCENERY_JUNGLE) {          /* high wooden footbridge just after the start */
        const TrackSample *a = &tr->s[(int)(0.026f*n)];
        float span = fmaxf(a->edge[0], a->edge[1]) + 9.0f, H = 8.5f;
        OBox(&db[1], SP(a, 0, H), a->right, span, 0.25f, 1.8f, WHITE);
        for (int sd = -1; sd <= 1; sd += 2) {
            for (int f = -1; f <= 1; f += 2) {
                Vector3 pc = Vector3Add(SP(a, sd*span, 0), Vector3Scale(a->fwd, f*1.6f));
                float ty = TerrainY(tr, pc.x, pc.z);
                pc.y = (ty + a->pos.y + H + 1.6f)*0.5f;
                OBox(&db[1], pc, a->right, 0.25f, (a->pos.y + H + 1.6f - ty)*0.5f, 0.25f, (Color){ 110, 76, 46, 255 });
            }
            Vector3 rc = Vector3Add(SP(a, 0, H + 1.2f), Vector3Scale(a->fwd, sd*1.7f));
            OBox(&db[4], rc, a->right, span, 0.06f, 0.06f, (Color){ 214, 182, 120, 255 });
            Vector3 rc2 = Vector3Add(SP(a, 0, H + 0.6f), Vector3Scale(a->fwd, sd*1.7f));
            OBox(&db[4], rc2, a->right, span, 0.05f, 0.05f, (Color){ 214, 182, 120, 255 });
        }
    }
    if (d->scenery == SCENERY_ISLAND) {          /* rock arch at the big cliff */
        const TrackSample *a = &tr->s[(int)(0.552f*n)];
        float R = a->width*0.5f + 5.0f;
        for (int sd = -1; sd <= 1; sd += 2) {
            Vector3 pc = SP(a, sd*(R + 1.5f), 0);
            float ty = TerrainY(tr, pc.x, pc.z);
            pc.y = (ty + a->pos.y + 9.0f)*0.5f;
            OBox(&db[3], pc, a->right, 3.0f, (a->pos.y + 9.0f - ty)*0.5f + 0.5f, 3.6f, rock);
        }
        for (int k = 0; k < 9; k++) {
            float t = PI*(k + 0.5f)/9.0f;
            Vector3 c = SP(a, -cosf(t)*(R + 1.5f), 8.5f + sinf(t)*4.5f);
            OBox(&db[3], c, a->right, (R + 1.5f)*PI/9.0f*0.62f, 2.0f, 3.4f, ColorScale(rock, 0.9f + 0.1f*sinf(k*1.7f)));
        }
        /* the secret cave through the cliff */
        for (int i = 0; i + 1 < tr->scN; i++) {
            const TrackSample *s0 = &tr->sc[i], *s1 = &tr->sc[i + 1];
            if (!scCover[i] || !scCover[i + 1]) continue;
            float w = tr->scHalf + 0.6f, H = 5.0f;
            Color cc = { 128, 112, 96, 255 };
            for (int sd = -1; sd <= 1; sd += 2)
                DQ(&db[3], SP(s0, sd*w, -0.3f), SP(s1, sd*w, -0.3f), SP(s1, sd*w, H), SP(s0, sd*w, H), s0->dist/5, s1->dist/5, 0, 1, cc, Vector3Add(s0->pos, Vector3Scale(s0->right, sd*30.0f)));
            DQ(&db[3], SP(s0, -w, H), SP(s0, w, H), SP(s1, w, H), SP(s1, -w, H), 0, 1, s0->dist/5, s1->dist/5, ColorScale(cc, 0.7f), Vector3Add(s0->pos, (Vector3){ 0, 60, 0 }));
            if (i == 0 || !scCover[i - 1]) Portal(&db[3], s0, w, H, w + 10, H + 3.5f, 3.0f, 1.0f, rock);
            if (i + 2 >= tr->scN || !scCover[i + 2]) Portal(&db[3], s1, w, H, w + 10, H + 3.5f, 3.0f, -1.0f, rock);
            if ((i % 6) == 0) {   /* glowing crystals */
                Vector3 c = SP(s0, (i & 1) ? w - 0.3f : -w + 0.3f, 3.2f);
                OBox(&db[4], c, s0->right, 0.25f, 0.5f, 0.25f, (Color){ 120, 255, 230, 255 });
            }
        }
        for (int i = 0; i + 1 < tr->scN; i++) {    /* the little kicker ramp into the cave */
            if (!tr->sc[i].ramp) continue;
            const TrackSample *s0 = &tr->sc[i], *s1 = &tr->sc[i + 1];
            float w = tr->scHalf;
            DQ(&db[0], SP(s0, -w, 0.03f), SP(s0, w, 0.03f), SP(s1, w, 0.03f), SP(s1, -w, 0.03f), 0, 1, s0->dist/4, s1->dist/4, WHITE, Vector3Add(s0->pos, (Vector3){ 0, -50, 0 }));
            for (int sd = -1; sd <= 1; sd += 2)
                DQ(&db[4], SP(s0, sd*w, 0.03f), SP(s1, sd*w, 0.03f), SP(s1, sd*w, -1.8f), SP(s0, sd*w, -1.8f), 0, 1, 0, 1, (Color){ 230, 120, 60, 255 }, s0->pos);
            if (i + 1 < tr->scN && !tr->sc[i + 1].ramp)
                DQ(&db[4], SP(s1, -w, -1.8f), SP(s1, w, -1.8f), SP(s1, w, 0.03f), SP(s1, -w, 0.03f), 0, 1, 0, 1, (Color){ 230, 120, 60, 255 }, Vector3Add(s1->pos, Vector3Scale(s1->fwd, -20)));
        }
    }
    static const int texs[5] = { TX_CHEVRON, TX_PLANK, TX_STONE, TX_ROCK, TX_GRAIN };
    for (int k = 0; k < 5; k++) { tr->mDeco[k] = MB_BuildModel(&db[k], G.tx[texs[k]], true); MB_Free(&db[k]); }
    tr->hasDeco = true;
}

void TrackBuild(Track *tr, int index)
{
    if (tr->loaded && tr->index == index && tr->builtVisual == G.settings.visualMode) return;
    if (tr->loaded) TrackUnload(tr);
    const TrackDef *d = &TRACK_DEFS[index];
    tr->def = d;
    tr->index = index;
    tr->builtVisual = G.settings.visualMode;

    /* --- dense spline + arc length --- */
    static float dense[MAX_CTRL_PTS*100][4];
    static float cum[MAX_CTRL_PTS*100 + 1];
    int m = SplineDense(d, dense, 100);
    cum[0] = 0;
    for (int i = 1; i <= m; i++) {
        const float *a = dense[i - 1], *b = dense[i % m];
        float dx = b[0] - a[0], dz = b[1] - a[1], dh = b[2] - a[2];
        cum[i] = cum[i - 1] + sqrtf(dx*dx + dz*dz + dh*dh);
    }
    tr->length = cum[m];
    int n = (int)(tr->length/2.0f);
    if (n > MAX_TRACK_SAMPLES) n = MAX_TRACK_SAMPLES;
    tr->n = n;
    tr->spacing = tr->length/n;
    int j = 0;
    for (int i = 0; i < n; i++) {
        float target = i*tr->spacing;
        while (j < m - 1 && cum[j + 1] < target) j++;
        float seg = cum[j + 1] - cum[j];
        float t = seg > 0 ? (target - cum[j])/seg : 0;
        const float *a = dense[j], *b = dense[(j + 1) % m];
        tr->s[i].pos = (Vector3){ a[0] + (b[0] - a[0])*t, a[2] + (b[2] - a[2])*t, a[1] + (b[1] - a[1])*t };
        tr->s[i].width = a[3] + (b[3] - a[3])*t;
        tr->s[i].dist = target;
        tr->s[i].ramp = false;
        tr->s[i].bump = false;
    }
    for (int i = 0; i < n; i++) {
        Vector3 pa = tr->s[(i - 1 + n) % n].pos, pb = tr->s[(i + 1) % n].pos;
        Vector3 f = { pb.x - pa.x, 0, pb.z - pa.z };
        f = Vector3Normalize(f);
        tr->s[i].fwd = f;
        tr->s[i].right = (Vector3){ -f.z, 0, f.x };
    }
    for (int i = 0; i < n; i++) {
        Vector3 f0 = tr->s[(i - 2 + n) % n].fwd, f1 = tr->s[(i + 2) % n].fwd;
        float da = WrapAngle(atan2f(f1.x, f1.z) - atan2f(f0.x, f0.z));
        tr->s[i].curv = da/(4.0f*tr->spacing);
    }
    /* v7 zones (tunnel, chevron floor, gorge gap, plank bridge, cave, open banks, hazards...) */
    for (int i = 0; i < n; i++) {
        float f = (float)i/n;
        tr->s[i].zone = 0;
        for (int z = 0; z < d->numZones; z++)
            if (f >= d->zones[z][0] && f < d->zones[z][1]) tr->s[i].zone |= (unsigned short)d->zones[z][2];
    }
    /* ramps: raise the road into a kicker, then a sudden drop */
    for (int r = 0; r < d->numRamps; r++) {
        int i0 = (int)(d->ramps[r][0]*n);
        int cnt = (int)(d->ramps[r][1]/tr->spacing);
        for (int k = 0; k < cnt; k++) {
            int idx = (i0 + k) % n;
            float f = (float)(k + 1)/cnt;
            tr->s[idx].pos.y += 2.4f*f*f*(3.0f - 2.0f*f)*0.6f + 2.4f*f*0.4f;
            tr->s[idx].ramp = true;
        }
    }
    /* moguls: rolling bumps that throw karts into the air at speed */
    for (int bi = 0; bi < d->numBumps; bi++) {
        int i0 = (int)(d->bumps[bi][0]*n), i1 = (int)(d->bumps[bi][1]*n);
        float total = (i1 - i0)*tr->spacing;
        for (int k = 0; k <= i1 - i0; k++) {
            int idx = (i0 + k) % n;
            float x = k*tr->spacing;
            float env = Clamp(fminf(x, total - x)/8.0f, 0, 1);
            float ph = x/d->bumpPeriod;
            float h = 0.5f - 0.5f*cosf(2*PI*ph);
            tr->s[idx].pos.y += d->bumpAmp*h*env;
            tr->s[idx].bump = true;
        }
    }
    float minY = 1e9f;
    tr->mapMin = (Vector2){ 1e9f, 1e9f }; tr->mapMax = (Vector2){ -1e9f, -1e9f };
    for (int i = 0; i < n; i++) {
        Vector3 p = tr->s[i].pos;
        if (p.y < minY) minY = p.y;
        if (p.x < tr->mapMin.x) tr->mapMin.x = p.x;
        if (p.z < tr->mapMin.y) tr->mapMin.y = p.z;
        if (p.x > tr->mapMax.x) tr->mapMax.x = p.x;
        if (p.z > tr->mapMax.y) tr->mapMax.y = p.z;
    }
    tr->groundY = minY - 0.45f;
    tr->shoulder = d->shoulderW > 0 ? d->shoulderW : d->rainbowRoad ? 1.6f : d->scenery == SCENERY_STADIUM ? 1.5f : 6.0f;
    /* wall lines: pull the inside of tight bends in so the off-road strip never folds over itself */
    {
        static float raw[MAX_TRACK_SAMPLES][2];
        for (int i = 0; i < n; i++) {
            float def = tr->s[i].width*0.5f + 1.0f + tr->shoulder;
            raw[i][0] = raw[i][1] = def;
            float c = tr->s[i].curv;
            if (fabsf(c) > 1e-4f) {
                float R = 1.0f/fabsf(c);
                float lim = fmaxf(R*0.8f - 0.5f, tr->s[i].width*0.5f + 2.0f);
                int inner = c > 0 ? 0 : 1;      /* left turn -> inside is the left */
                if (lim < raw[i][inner]) raw[i][inner] = lim;
            }
            /* boxed-in sections: walls hug the road */
            if (tr->s[i].zone & (ZN_TUNNEL | ZN_PLANKS | ZN_GAP | ZN_CAVE | ZN_BOOSTFLOOR)) raw[i][0] = raw[i][1] = tr->s[i].width*0.5f + 1.0f;
        }
        int win = d->numZones > 0 ? 14 : 5;
        for (int i = 0; i < n; i++) for (int sd = 0; sd < 2; sd++) {
            float m = raw[i][sd];
            for (int k = -win; k <= win; k++) m = fminf(m, raw[(i + k + n) % n][sd] + fabsf((float)k)*0.6f);
            tr->s[i].edge[sd] = m;
        }
    }
    BuildShortcut(tr);
    /* overpasses: samples with a much lower, unrelated part of the course right underneath */
    for (int i = 0; i < n; i++) {
        tr->s[i].bridge = false;
        if (d->scenery != SCENERY_STADIUM) continue;
        for (int k = 0; k < n; k += 2) {
            int gap = abs(i - k); if (gap > n/2) gap = n - gap;
            if (gap < 40 || tr->s[k].pos.y > tr->s[i].pos.y - 3.0f) continue;
            float dx = tr->s[i].pos.x - tr->s[k].pos.x, dz = tr->s[i].pos.z - tr->s[k].pos.z;
            float lim = tr->s[k].width*0.5f + 1.0f + STADIUM_BANK_W + 1.5f;
            if (dx*dx + dz*dz < lim*lim) { tr->s[i].bridge = true; break; }
        }
    }
    BuildTerrain(tr);
    bool spooky = d->scenery == SCENERY_SPOOKY;
    bool stadium = d->scenery == SCENERY_STADIUM;
    bool trail = d->scenery == SCENERY_JUNGLE || d->scenery == SCENERY_ISLAND || d->scenery == SCENERY_FARM;

    /* --- road surface --- */
    MeshBuilder mb; MB_Init(&mb);
    MeshBuilder cb; MB_Init(&cb);        /* curbs + start line */
    for (int i = 0; i < n; i++) {
        int i1 = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[i1];
        unsigned short zab = a->zone | b->zone;
        if (zab & ZN_GAP) continue;                       /* the gorge: nothing to drive on */
        bool decoFloor = (zab & (ZN_BOOSTFLOOR | ZN_PLANKS)) != 0;   /* chevrons / planks are in mDeco */
        float da = a->dist, db = (i1 == 0 ? tr->length : b->dist);
        float ha = a->width*0.5f, hb = b->width*0.5f;
        Vector3 below = Vector3Add(a->pos, (Vector3){ 0, -50, 0 });
        Color rc = d->road;
        float va = da/10.0f, vb = db/10.0f, uw = 1.0f;
        if (d->rainbowRoad) { rc = HueColor(da/tr->length*360.0f*5.0f, 0.6f, 1.0f); va = da/18.0f; vb = db/18.0f; uw = 2.0f; }
        if (spooky) { rc = (Color){ 248, 236, 222, 255 }; va = da/6.0f; vb = db/6.0f; uw = 3.0f; }
        if (stadium || trail) { va = da/6.0f; vb = db/6.0f; uw = 3.0f; }
        if (a->bump && stadium) {
            float rel = Clamp((a->pos.y - Lerp(tr->s[(i + n - 3) % n].pos.y, tr->s[(i + 3) % n].pos.y, 0.5f))/fmaxf(d->bumpAmp*0.25f, 0.05f), -1, 1);
            rc = ColorScale(rc, 0.86f + 0.2f*rel);     /* crests catch the light, troughs stay dark */
        } else if (a->bump) rc = ColorScale(rc, 0.94f + 0.12f*Clamp((a->pos.y - Lerp(tr->s[(i + n - 6) % n].pos.y, tr->s[(i + 6) % n].pos.y, 0.5f))/fmaxf(d->bumpAmp, 0.1f), 0, 1));
        if (a->ramp) rc = stadium ? ColorScale(d->road, ((i/2) & 1) ? 1.12f : 1.0f) : ((i/2) & 1) ? (Color){ 255, 205, 30, 255 } : (Color){ 70, 70, 75, 255 };
        if (i == 0 || i == 1) {
            int cells = 16;
            for (int c = 0; c < cells; c++) {
                float t0 = -1.0f + 2.0f*c/cells, t1 = -1.0f + 2.0f*(c + 1)/cells;
                Vector3 p0 = Vector3Add(a->pos, Vector3Scale(a->right, ha*t0)), p1 = Vector3Add(a->pos, Vector3Scale(a->right, ha*t1));
                Vector3 p2 = Vector3Add(b->pos, Vector3Scale(b->right, hb*t1)), p3 = Vector3Add(b->pos, Vector3Scale(b->right, hb*t0));
                Color cc = ((c + i) & 1) ? (Color){ 25, 25, 30, 255 } : (Color){ 255, 255, 255, 255 };
                MB_QuadUV(&cb, p0, p1, p2, p3, (Vector2){ 0.4f, 0 }, (Vector2){ 0.6f, 0 }, (Vector2){ 0.6f, 1 }, (Vector2){ 0.4f, 1 }, cc, below, true);
            }
        } else {
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -ha)), r0 = Vector3Add(a->pos, Vector3Scale(a->right, ha));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -hb)), r1 = Vector3Add(b->pos, Vector3Scale(b->right, hb));
            if (d->rainbowRoad && !a->ramp) {
                /* rainbow lanes across the width (the shader also cycles the hue over time) */
                const int L = 6;
                for (int l = 0; l < L; l++) {
                    float t0 = (float)l/L, t1 = (float)(l + 1)/L;
                    Vector3 q0 = Vector3Lerp(l0, r0, t0), q1 = Vector3Lerp(l0, r0, t1), q2 = Vector3Lerp(l1, r1, t1), q3 = Vector3Lerp(l1, r1, t0);
                    Color lc = HueColor(l*360.0f/L + da*0.8f, 0.55f, 1.0f);
                    MB_QuadUV(&mb, q0, q1, q2, q3, (Vector2){ uw*t0, va }, (Vector2){ uw*t1, va }, (Vector2){ uw*t1, vb }, (Vector2){ uw*t0, vb }, lc, below, true);
                }
            } else if (!decoFloor)
            MB_QuadUV(&mb, l0, r0, r1, l1, (Vector2){ 0, va }, (Vector2){ uw, va }, (Vector2){ uw, vb }, (Vector2){ 0, vb }, rc, below, true);
        }
        if (zab & ZN_PLANKS) continue;
        /* raised, rounded curbs */
        Color rum = ((i/2) & 1) ? d->rumbleA : d->rumbleB;
        if (d->rainbowRoad) rum = ((i/2) & 1) ? WHITE : HueColor(a->dist*2.0f, 0.45f, 1.0f);
        float prof[4] = { 0.0f, 0.075f, 0.075f, 0.02f }, offs[4] = { 0.0f, 0.3f, 0.7f, 1.0f };
        for (int sd = -1; sd <= 1; sd += 2) {
            for (int k = 0; k < 3; k++) {
                Vector3 i0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*(ha + offs[k]))), o0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*(ha + offs[k + 1])));
                Vector3 i1v = Vector3Add(b->pos, Vector3Scale(b->right, sd*(hb + offs[k]))), o1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*(hb + offs[k + 1])));
                i0.y += prof[k]; i1v.y += prof[k]; o0.y += prof[k + 1]; o1.y += prof[k + 1];
                MB_QuadUV(&cb, i0, o0, o1, i1v, (Vector2){ offs[k], da/4.0f }, (Vector2){ offs[k + 1], da/4.0f }, (Vector2){ offs[k + 1], db/4.0f }, (Vector2){ offs[k], db/4.0f }, rum, below, true);
            }
        }
        if ((a->ramp || b->ramp) && !stadium) {
            for (int sd = -1; sd <= 1; sd += 2) {
                Vector3 e0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*(ha + 1.0f))), e1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*(hb + 1.0f)));
                Vector3 g0 = e0, g1 = e1; g0.y -= 3.0f; g1.y -= 3.0f;
                MB_QuadUV(&cb, e0, e1, g1, g0, (Vector2){ 0.5f, 0 }, (Vector2){ 0.5f, 1 }, (Vector2){ 0.5f, 1 }, (Vector2){ 0.5f, 0 }, ((i/2) & 1) ? (Color){ 255, 205, 30, 255 } : (Color){ 70, 70, 75, 255 }, a->pos, true);
            }
        }
    }
    if (d->scIsRoad) {
        for (int i = 0; i + 1 < tr->scN; i++) {
            const TrackSample *a = &tr->sc[i], *b = &tr->sc[i + 1];
            if (InMainCorridor(tr, a->pos, -1.5f) && InMainCorridor(tr, b->pos, -1.5f)) continue;
            float hh = tr->scHalf;
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -hh)), r0 = Vector3Add(a->pos, Vector3Scale(a->right, hh));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -hh)), r1 = Vector3Add(b->pos, Vector3Scale(b->right, hh));
            l0.y += 0.05f; r0.y += 0.05f; l1.y += 0.05f; r1.y += 0.05f;
            Color rc = stadium ? ColorScale(d->road, 0.8f) : d->followTerrain ? ColorScale(d->road, (i & 1) ? 0.78f : 0.84f) : HueColor(i*9.0f, 0.4f, 1.0f);
            MB_QuadUV(&mb, l0, r0, r1, l1, (Vector2){ 0, a->dist/18 }, (Vector2){ 1, a->dist/18 }, (Vector2){ 1, b->dist/18 }, (Vector2){ 0, b->dist/18 },
                      rc, Vector3Add(a->pos, (Vector3){ 0, -50, 0 }), true);
        }
    }
    tr->mRoad = MB_BuildModel(&mb, d->rainbowRoad ? G.tx[TX_RAINBOW] : spooky ? G.tx[TX_WOOD] : stadium ? G.tx[TX_DIRT] : trail ? G.tx[TX_TRAIL] : G.texRoad, true);
    MB_Free(&mb);
    tr->mCurb = MB_BuildModel(&cb, G.tx[TX_CURB], true);
    MB_Free(&cb);

    /* --- shoulders, embankments and terrain (ground texture) + walls --- */
    MeshBuilder gb; MB_Init(&gb);
    MeshBuilder wb; MB_Init(&wb);
    Color gc = WHITE;
    const float GUV = 7.0f;
    for (int i = 0; i < n; i++) {
        int i1 = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[i1];
        Vector3 below = Vector3Add(a->pos, (Vector3){ 0, -50, 0 });
        if ((a->zone | b->zone) & (ZN_GAP | ZN_PLANKS)) continue;
        for (int sd = -1; sd <= 1; sd += 2) {
            float ia = a->width*0.5f + 1.0f, ib = b->width*0.5f + 1.0f;
            int si = sd > 0 ? 1 : 0;
            Vector3 p0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*ia)), p1 = Vector3Add(a->pos, Vector3Scale(a->right, sd*a->edge[si]));
            Vector3 p2 = Vector3Add(b->pos, Vector3Scale(b->right, sd*b->edge[si])), p3 = Vector3Add(b->pos, Vector3Scale(b->right, sd*ib));
            Color sc = d->rainbowRoad ? (Color){ 90, 70, 140, 255 } : gc;
            MB_QuadUV(&gb, p0, p1, p2, p3, (Vector2){ p0.x/GUV, p0.z/GUV }, (Vector2){ p1.x/GUV, p1.z/GUV }, (Vector2){ p2.x/GUV, p2.z/GUV }, (Vector2){ p3.x/GUV, p3.z/GUV }, sc, below, true);
        }
    }
    if (!d->scIsRoad) {
        Color tc = d->scenery == SCENERY_SNOW ? (Color){ 205, 220, 245, 255 } : d->scenery == SCENERY_DESERT ? (Color){ 200, 150, 95, 255 } :
                   d->scenery == SCENERY_BEACH ? (Color){ 255, 240, 205, 255 } : spooky ? (Color){ 160, 140, 125, 255 } : (Color){ 185, 140, 90, 255 };
        for (int i = 0; i + 1 < tr->scN; i++) {
            const TrackSample *a = &tr->sc[i], *b = &tr->sc[i + 1];
            if (InMainCorridor(tr, a->pos, -1.5f) && InMainCorridor(tr, b->pos, -1.5f)) continue;
            float hh = tr->scHalf;
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -hh)), r0 = Vector3Add(a->pos, Vector3Scale(a->right, hh));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -hh)), r1 = Vector3Add(b->pos, Vector3Scale(b->right, hh));
            l0.y += 0.05f; r0.y += 0.05f; l1.y += 0.05f; r1.y += 0.05f;
            MB_QuadUV(&gb, l0, r0, r1, l1, (Vector2){ l0.x/GUV, l0.z/GUV }, (Vector2){ r0.x/GUV, r0.z/GUV }, (Vector2){ r1.x/GUV, r1.z/GUV }, (Vector2){ l1.x/GUV, l1.z/GUV },
                      tc, Vector3Add(a->pos, (Vector3){ 0, -50, 0 }), true);
        }
    }

    /* walls: painted barrier panels with a rounded top (stone on Ghoulwood, neon on Starlight) */
    float wh = d->wallHeight - 0.3f;
    int wallTex = spooky ? TX_STONE : d->rainbowRoad ? TX_GRAIN : stadium ? TX_ARENA : TX_BARRIER;
    if (d->numZones) wallTex = d->wallStyle == WS_LOG ? TX_BARK : d->wallStyle == WS_FENCE ? TX_WOOD : TX_GRAIN;
    if (stadium) BuildStadiumBarriers(tr, &wb);
    else {
    Color skirtC = d->scenery == SCENERY_MEADOW ? (Color){ 225, 235, 225, 255 } : WHITE;
    for (int i = 0; i < n; i++) {
        int i1 = (i + 1) % n;
        const TrackSample *a = &tr->s[i], *b = &tr->s[i1];
        Color wc = ((i/4) & 1) ? d->wallA : d->wallB;
        if (d->rainbowRoad) wc = HueColor(a->dist*1.5f + 180.0f, 0.55f, 1.0f);
        if (spooky) wc = ColorMix(d->wallA, WHITE, 0.25f);
        unsigned short zab = a->zone | b->zone;
        bool checker = false;
        wh = d->wallHeight - 0.3f;
        if (d->numZones) {
            if (zab & (ZN_GAP | ZN_PLANKS | ZN_TUNNEL | ZN_CAVE | ZN_BOOSTFLOOR)) continue;
            if (d->wallStyle == WS_NONE) continue;
            if (d->wallStyle == WS_RACEWAY) {
                checker = (zab & ZN_CHECKER) != 0;
                wh = checker ? 0.85f : 0.45f;
                wc = checker ? (((i/2) & 1) ? d->wallA : d->wallB) : (Color){ 176, 180, 188, 255 };
            } else wc = ((i/3) & 1) ? d->wallA : d->wallB;
        }
        Color wcI = wc; float whI = wh; bool checkerI = checker;
        for (int sd = -1; sd <= 1; sd += 2) {
            Color wc = wcI; float wh = whI; bool checker = checkerI;
            if (sd < 0 && (zab & ZN_LOWWALL_L)) { checker = false; wh = 0.45f; wc = (Color){ 176, 180, 188, 255 }; }
            if (sd < 0 && (zab & ZN_OPEN_L)) continue;
            if (sd > 0 && (zab & ZN_OPEN_R)) continue;
            float oa = a->edge[sd > 0 ? 1 : 0], ob = b->edge[sd > 0 ? 1 : 0];
            Vector3 in0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*oa)), in1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*ob));
            if (InShortcut(tr, in0, 0.6f) || InShortcut(tr, in1, 0.6f) || InShortcut(tr, Vector3Lerp(in0, in1, 0.5f), 0.6f)) continue; /* the secret gap */
            Vector3 out0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*(oa + 0.8f))), out1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*(ob + 0.8f)));
            Vector3 ti0 = { in0.x, in0.y + wh, in0.z }, ti1 = { in1.x, in1.y + wh, in1.z };
            Vector3 to0 = { out0.x, out0.y + wh, out0.z }, to1 = { out1.x, out1.y + wh, out1.z };
            Vector3 farOut = Vector3Add(a->pos, Vector3Scale(a->right, sd*(oa + 30)));
            float ua, ub, vt, vbm;
            if (wallTex == TX_BARRIER) {
                ua = sd < 0 ? i/16.0f : -i/16.0f; ub = sd < 0 ? (i + 1)/16.0f : -(i + 1)/16.0f;
                vt = sd < 0 ? 0.02f : 0.52f; vbm = sd < 0 ? 0.48f : 0.98f;
            } else {
                ua = a->dist/4.0f*(sd < 0 ? 1 : -1); ub = (i1 == 0 ? tr->length : b->dist)/4.0f*(sd < 0 ? 1 : -1);
                vt = 0; vbm = wh/4.0f;
            }
            if (checker) {   /* two rows of red / white blocks */
                Vector3 m0 = Vector3Lerp(in0, ti0, 0.5f), m1 = Vector3Lerp(in1, ti1, 0.5f);
                Color c2 = ((i/2) & 1) ? d->wallB : d->wallA;
                MB_QuadUV(&wb, in0, in1, m1, m0, (Vector2){ ua, vbm }, (Vector2){ ub, vbm }, (Vector2){ ub, vt }, (Vector2){ ua, vt }, wc, farOut, true);
                MB_QuadUV(&wb, m0, m1, ti1, ti0, (Vector2){ ua, vbm }, (Vector2){ ub, vbm }, (Vector2){ ub, vt }, (Vector2){ ua, vt }, c2, farOut, true);
                wc = c2;
            } else
            MB_QuadUV(&wb, in0, in1, ti1, ti0, (Vector2){ ua, vbm }, (Vector2){ ub, vbm }, (Vector2){ ub, vt }, (Vector2){ ua, vt }, wc, farOut, true);
            /* rounded cap: half-cylinder along the wall top */
            Vector3 acrossA = Vector3Scale(a->right, (float)sd), acrossB = Vector3Scale(b->right, (float)sd);
            Vector3 mA = Vector3Lerp(ti0, to0, 0.5f), mB = Vector3Lerp(ti1, to1, 0.5f);
            int cs = G.settings.visualMode == 1 ? 6 : 4;
            Color capC = ColorScale(wc, 1.08f);
            for (int k = 0; k < cs; k++) {
                float t0 = PI - PI*k/cs, t1 = PI - PI*(k + 1)/cs;
                Vector3 nA0 = Vector3Add(Vector3Scale(acrossA, cosf(t0)), (Vector3){ 0, sinf(t0), 0 }), nA1 = Vector3Add(Vector3Scale(acrossA, cosf(t1)), (Vector3){ 0, sinf(t1), 0 });
                Vector3 nB0 = Vector3Add(Vector3Scale(acrossB, cosf(t0)), (Vector3){ 0, sinf(t0), 0 }), nB1 = Vector3Add(Vector3Scale(acrossB, cosf(t1)), (Vector3){ 0, sinf(t1), 0 });
                Vector3 pA0 = Vector3Add(mA, Vector3Scale(nA0, 0.4f)), pA1 = Vector3Add(mA, Vector3Scale(nA1, 0.4f));
                Vector3 pB0 = Vector3Add(mB, Vector3Scale(nB0, 0.4f)), pB1 = Vector3Add(mB, Vector3Scale(nB1, 0.4f));
                Vector2 uvA = { ua, vt }, uvB = { ub, vt };
                if (sd > 0) { /* keep CCW winding seen from outside */
                    MB_VertexLit(&wb, pA0, uvA, nA0, capC); MB_VertexLit(&wb, pB1, uvB, nB1, capC); MB_VertexLit(&wb, pA1, uvA, nA1, capC);
                    MB_VertexLit(&wb, pA0, uvA, nA0, capC); MB_VertexLit(&wb, pB0, uvB, nB0, capC); MB_VertexLit(&wb, pB1, uvB, nB1, capC);
                } else {
                    MB_VertexLit(&wb, pA0, uvA, nA0, capC); MB_VertexLit(&wb, pA1, uvA, nA1, capC); MB_VertexLit(&wb, pB1, uvB, nB1, capC);
                    MB_VertexLit(&wb, pA0, uvA, nA0, capC); MB_VertexLit(&wb, pB1, uvB, nB1, capC); MB_VertexLit(&wb, pB0, uvB, nB0, capC);
                }
            }
            /* outer embankment down to the terrain (grass texture) or into the void */
            float dropA = d->noGround ? 2.5f : d->followTerrain ? 0.6f : (a->pos.y - tr->groundY);
            float dropB = d->noGround ? 2.5f : d->followTerrain ? 0.6f : (b->pos.y - tr->groundY);
            Vector3 g0 = Vector3Add(out0, Vector3Scale(a->right, sd*(d->noGround ? 0.0f : dropA*1.3f + 0.5f)));
            Vector3 g1 = Vector3Add(out1, Vector3Scale(b->right, sd*(d->noGround ? 0.0f : dropB*1.3f + 0.5f)));
            if (d->noGround) { g0.y = out0.y - dropA - 0.05f; g1.y = out1.y - dropB - 0.05f;
                MB_QuadUV(&wb, to0, to1, g1, g0, (Vector2){ ua, vt }, (Vector2){ ub, vt }, (Vector2){ ub, vbm }, (Vector2){ ua, vbm }, ColorScale(wc, 0.5f), Vector3Add(a->pos, Vector3Scale(a->right, -sd*20.0f)), true);
            } else {
                float gl0 = d->followTerrain ? out0.y - 0.3f : tr->groundY, gl1 = d->followTerrain ? out1.y - 0.3f : tr->groundY;
                g0.y = fminf(TerrainY(tr, g0.x, g0.z), gl0) - 0.05f; g1.y = fminf(TerrainY(tr, g1.x, g1.z), gl1) - 0.05f;
                MB_QuadUV(&gb, to0, to1, g1, g0, (Vector2){ to0.x/GUV, to0.z/GUV }, (Vector2){ to1.x/GUV, to1.z/GUV }, (Vector2){ g1.x/GUV, g1.z/GUV }, (Vector2){ g0.x/GUV, g0.z/GUV },
                          skirtC, Vector3Add(a->pos, Vector3Scale(a->right, -sd*20.0f)), true);
            }
        }
        if (d->noGround) {
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -(a->edge[0] + 0.8f))), r0 = Vector3Add(a->pos, Vector3Scale(a->right, a->edge[1] + 0.8f));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -(b->edge[0] + 0.8f))), r1 = Vector3Add(b->pos, Vector3Scale(b->right, b->edge[1] + 0.8f));
            l0.y -= 2.55f; r0.y -= 2.55f; l1.y -= 2.55f; r1.y -= 2.55f;
            MB_QuadUV(&wb, l0, r0, r1, l1, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, (Color){ 70, 50, 130, 255 }, Vector3Add(a->pos, (Vector3){ 0, 50, 0 }), true);
        }
    }
    /* shortcut fences + causeway sides */
    for (int i = 0; i + 1 < tr->scN && !stadium; i++) {
        const TrackSample *a = &tr->sc[i], *b = &tr->sc[i + 1];
        for (int sd = -1; sd <= 1; sd += 2) {
            Vector3 in0 = Vector3Add(a->pos, Vector3Scale(a->right, sd*tr->scHalf)), in1 = Vector3Add(b->pos, Vector3Scale(b->right, sd*tr->scHalf));
            if (InMainCorridor(tr, in0, 0.5f) || InMainCorridor(tr, in1, 0.5f)) continue;
            float fh = 0.7f;
            Color fc = d->scIsRoad ? (d->followTerrain ? ((i & 1) ? (Color){ 168, 140, 104, 255 } : (Color){ 150, 122, 90, 255 }) : HueColor(i*12.0f, 0.45f, 1.0f)) : ((i & 1) ? (Color){ 190, 130, 80, 255 } : (Color){ 160, 105, 60, 255 });
            Vector3 t0 = { in0.x, in0.y + fh, in0.z }, t1 = { in1.x, in1.y + fh, in1.z };
            Vector3 out0 = Vector3Add(in0, Vector3Scale(a->right, sd*0.5f)), out1 = Vector3Add(in1, Vector3Scale(b->right, sd*0.5f));
            Vector3 to0 = { out0.x, out0.y + fh, out0.z }, to1 = { out1.x, out1.y + fh, out1.z };
            Vector2 z0 = { 0.0f, 0.03f }, z1 = { 0.05f, 0.03f };
            MB_QuadUV(&wb, in0, in1, t1, t0, z0, z1, z1, z0, fc, Vector3Add(a->pos, Vector3Scale(a->right, sd*30)), true);
            MB_QuadUV(&wb, t0, t1, to1, to0, z0, z1, z1, z0, ColorScale(fc, 1.1f), Vector3Add(a->pos, (Vector3){ 0, -50, 0 }), true);
            float drop = d->noGround ? 2.5f : d->followTerrain ? 0.8f : (a->pos.y - tr->groundY);
            Vector3 g0 = Vector3Add(out0, Vector3Scale(a->right, sd*(d->noGround ? 0 : drop*1.3f)));
            Vector3 g1 = Vector3Add(out1, Vector3Scale(b->right, sd*(d->noGround ? 0 : drop*1.3f)));
            g0.y = out0.y - drop - 0.05f; g1.y = out1.y - drop - 0.05f;
            if (d->noGround) MB_QuadUV(&wb, out0, out1, g1, g0, z0, z1, z1, z0, (Color){ 70, 50, 130, 255 }, Vector3Add(a->pos, Vector3Scale(a->right, -sd*20.0f)), true);
            else MB_QuadUV(&gb, out0, out1, g1, g0, (Vector2){ out0.x/GUV, out0.z/GUV }, (Vector2){ out1.x/GUV, out1.z/GUV }, (Vector2){ g1.x/GUV, g1.z/GUV }, (Vector2){ g0.x/GUV, g0.z/GUV },
                           skirtC, Vector3Add(a->pos, Vector3Scale(a->right, -sd*20.0f)), true);
        }
        if (d->noGround) {
            Vector3 l0 = Vector3Add(a->pos, Vector3Scale(a->right, -(tr->scHalf + 0.5f))), r0 = Vector3Add(a->pos, Vector3Scale(a->right, tr->scHalf + 0.5f));
            Vector3 l1 = Vector3Add(b->pos, Vector3Scale(b->right, -(tr->scHalf + 0.5f))), r1 = Vector3Add(b->pos, Vector3Scale(b->right, tr->scHalf + 0.5f));
            l0.y -= 2.55f; r0.y -= 2.55f; l1.y -= 2.55f; r1.y -= 2.55f;
            MB_QuadUV(&wb, l0, r0, r1, l1, (Vector2){ 0, 0 }, (Vector2){ 1, 0 }, (Vector2){ 1, 1 }, (Vector2){ 0, 1 }, (Color){ 70, 50, 130, 255 }, Vector3Add(a->pos, (Vector3){ 0, 50, 0 }), true);
        }
    }
    }   /* !stadium */
    tr->mWalls = MB_BuildModel(&wb, G.tx[wallTex], true);
    MB_Free(&wb);

    if (!d->noGround) {
        /* terrain grid: smooth normals, near/far colour gradient, macro variation */
        static float gd[TGMAX + 1][TGMAX + 1];
        for (int gx = 0; gx <= TG; gx++) for (int gz = 0; gz <= TG; gz++) {
            float x = tX0 + (tX1 - tX0)*gx/TG, z = tZ0 + (tZ1 - tZ0)*gz/TG;
            gd[gx][gz] = TrackDist(tr, x, z);
        }
        Color nearC = ColorScale(gc, 0.96f);
        Color farC = nearC;
        if (d->groundFar.a) {
            farC = (Color){ (unsigned char)Clamp(255.0f*d->groundFar.r/fmaxf(d->ground.r, 1), 0, 255),
                            (unsigned char)Clamp(255.0f*d->groundFar.g/fmaxf(d->ground.g, 1), 0, 255),
                            (unsigned char)Clamp(255.0f*d->groundFar.b/fmaxf(d->ground.b, 1), 0, 255), 255 };
            farC = ColorScale(farC, 0.96f);
        }
        float cx = (tX1 - tX0)/TG, cz = (tZ1 - tZ0)/TG;
        unsigned int sd = 1500u + (unsigned)index*7u;
        for (int gx = 0; gx < TG; gx++) for (int gz = 0; gz < TG; gz++) {
            Vector3 p[4]; Color c[4]; Vector2 uv[4]; Vector3 nn[4];
            int ix[4] = { gx, gx + 1, gx + 1, gx }, iz[4] = { gz, gz, gz + 1, gz + 1 };
            for (int k = 0; k < 4; k++) {
                int X = ix[k], Z = iz[k];
                float x = tX0 + cx*X, z = tZ0 + cz*Z;
                float f = Clamp((gd[X][Z] - d->farStart)/fmaxf(d->farEnd - d->farStart, 1), 0, 1);
                f = f*f*(3 - 2*f);
                float h = TH[X][Z];
                p[k] = (Vector3){ x, h, z };
                float hl = TH[X > 0 ? X - 1 : X][Z], hr = TH[X < TG ? X + 1 : X][Z], hd = TH[X][Z > 0 ? Z - 1 : Z], hu = TH[X][Z < TG ? Z + 1 : Z];
                nn[k] = Vector3Normalize((Vector3){ -(hr - hl)/(2*cx), 1.0f, -(hu - hd)/(2*cz) });
                Color col = ColorMix(nearC, farC, f);
                float mac = 0.9f + 0.2f*WorldNoise(x/28.0f, z/28.0f, sd);
                col = ColorScale(col, mac);
                float rel = h - tr->groundY;
                if (d->scenery == SCENERY_MEADOW && rel > 6) col = ColorMix(col, (Color){ 255, 255, 200, 255 }, Clamp((rel - 6)/30.0f, 0, 0.3f));
                if (d->scenery == SCENERY_SNOW && rel > 25) col = ColorMix(col, WHITE, Clamp((rel - 25)/30.0f, 0, 0.6f));
                if (stadium) {   /* packed dirt: darker, redder slopes; dusty tops */
                    col = ColorScale(gc, 0.62f + 0.3f*nn[k].y*nn[k].y + 0.06f*Clamp(h/6.0f, 0, 1));
                    col = ColorScale(col, mac);
                }
                if (d->followTerrain) {   /* earthy cut banks; farm fields; sandy beaches */
                    static const Color earth[4] = { { 160, 150, 128, 255 }, { 140, 100, 64, 255 }, { 170, 150, 120, 255 }, { 176, 130, 86, 255 } };
                    int ei = d->scenery == SCENERY_JUNGLE ? 1 : d->scenery == SCENERY_ISLAND ? 2 : d->scenery == SCENERY_FARM ? 3 : 0;
                    col = ColorMix(col, earth[ei], Clamp((0.86f - nn[k].y)*3.0f, 0, 0.75f));
                    if (d->scenery == SCENERY_FARM && gd[X][Z] > 34) {
                        int fx = (int)floorf(x/72.0f), fz = (int)floorf(z/56.0f);
                        unsigned int hsh = ((unsigned)fx*73856093u) ^ ((unsigned)fz*19349663u);
                        int t = (int)((hsh >> 4) % 4u);
                        if (t == 1) col = ColorMix(col, (Color){ 255, 222, 110, 255 }, 0.5f);       /* wheat */
                        else if (t == 2) col = ColorMix(col, (Color){ 168, 120, 78, 255 }, 0.45f);  /* ploughed */
                        else if (t == 3) col = ColorScale(col, 0.82f);
                    }
                    if (d->scenery == SCENERY_ISLAND && !InsideLoop(tr, x, z) && gd[X][Z] > 10) col = ColorMix(col, (Color){ 255, 240, 200, 255 }, 0.35f);
                }
                if (tr->hasWater && h < tr->waterY) col = ColorMix(col, (Color){ 120, 200, 210, 255 }, Clamp((tr->waterY - h)/3.0f, 0, 0.8f));
                c[k] = col;
                uv[k] = (Vector2){ x/GUV, z/GUV };
            }
            MB_VertexLit(&gb, p[0], uv[0], nn[0], c[0]); MB_VertexLit(&gb, p[2], uv[2], nn[2], c[2]); MB_VertexLit(&gb, p[1], uv[1], nn[1], c[1]);
            MB_VertexLit(&gb, p[0], uv[0], nn[0], c[0]); MB_VertexLit(&gb, p[3], uv[3], nn[3], c[3]); MB_VertexLit(&gb, p[2], uv[2], nn[2], c[2]);
        }
    }
    tr->mGround = MB_BuildModel(&gb, G.texGround[index], true);
    MB_Free(&gb);

    /* water plane (sea / lakes), animated in the shader */
    MB_Init(&mb);
    if (tr->hasWater) {
        int wn = 12;
        for (int a = 0; a < wn; a++) for (int b = 0; b < wn; b++) {
            float x0 = tX0 + (tX1 - tX0)*a/wn, x1 = tX0 + (tX1 - tX0)*(a + 1)/wn, z0 = tZ0 + (tZ1 - tZ0)*b/wn, z1 = tZ0 + (tZ1 - tZ0)*(b + 1)/wn;
            Vector3 p0 = { x0, tr->waterY, z0 }, p1 = { x1, tr->waterY, z0 }, p2 = { x1, tr->waterY, z1 }, p3 = { x0, tr->waterY, z1 };
            MB_QuadUV(&mb, p0, p1, p2, p3, (Vector2){ x0/16, z0/16 }, (Vector2){ x1/16, z0/16 }, (Vector2){ x1/16, z1/16 }, (Vector2){ x0/16, z1/16 }, WHITE, (Vector3){ 0, -1000, 0 }, false);
        }
    }
    tr->mWater = MB_BuildModel(&mb, G.tx[TX_WATER], true);
    MB_Free(&mb);

    BuildDeco(tr);
    BuildSceneryChunks(tr);
    MB_Init(&mb);
    tr->mScenery = MB_BuildModel(&mb, G.texWhite, true);     /* (legacy, empty) */
    MB_Free(&mb);

    MB_Init(&mb); BuildSky(tr, &mb); tr->mSky = MB_BuildModel(&mb, G.texWhite, false); MB_Free(&mb);
    MB_Init(&mb); BuildClouds(tr, &mb); tr->mClouds = MB_BuildModel(&mb, G.tx[TX_CLOUD], false); MB_Free(&mb);
    MB_Init(&mb); BuildPano(tr, &mb); tr->mPano = MB_BuildModel(&mb, TexturePanorama(index), false); MB_Free(&mb);

    tr->loaded = true;
    TraceLog(LOG_INFO, "TRACK: built '%s' (%d samples, length %.0f, %d scenery vertices)", d->name, n, tr->length, tr->sceneVerts);
}

void SceneryUnload(Track *tr);
void TrackUnload(Track *tr)
{
    if (!tr->loaded) return;
    UnloadModel(tr->mRoad); UnloadModel(tr->mGround); UnloadModel(tr->mWalls);
    UnloadModel(tr->mScenery); UnloadModel(tr->mSky);
    UnloadModel(tr->mCurb); UnloadModel(tr->mWater); UnloadModel(tr->mClouds); UnloadModel(tr->mPano);
    if (tr->hasDeco) for (int k = 0; k < 5; k++) UnloadModel(tr->mDeco[k]);
    tr->hasDeco = false;
    SceneryUnload(tr);
    tr->loaded = false;
}
