# HudOverlay.gd — broadcast-style HUD drawn in one Control: scorebug, event banner, shot-power meter and
# a radar mini-map. Reads state from the game node (`boot`) every frame; owns no game logic.
extends Control

var boot: Node
var banner_text := ""
var banner_time := 0.0
var banner_col := Color("#ffffff")
const BANNERS := {"GOAL": ["GOAL!", Color("#ffd166")], "Great save": ["GREAT SAVE", Color("#7bdff2")],
	"Foul": ["FOUL", Color("#ff6b6b")], "woodwork": ["OFF THE WOODWORK!", Color("#ffd166")], "Off the bar": ["OFF THE BAR!", Color("#ffd166")],
	"Corner": ["CORNER", Color("#ffffff")], "Throw-in": ["THROW-IN", Color("#ffffff")], "Goal kick": ["GOAL KICK", Color("#ffffff")],
	"Kick off": ["KICK OFF", Color("#2bdb85")], "Free kick": ["FREE KICK", Color("#ffffff")]}

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func show_banner(text: String) -> void:
	for k in BANNERS:
		if text.contains(k):
			banner_text = BANNERS[k][0]
			banner_col = BANNERS[k][1]
			banner_time = 2.2 if k == "GOAL" else 1.4
			return

func _process(delta: float) -> void:
	banner_time = maxf(0.0, banner_time - delta)
	if visible:
		queue_redraw()

func _font() -> Font:
	return ThemeDB.fallback_font

func _text(pos: Vector2, s: String, size: int, col: Color, align := HORIZONTAL_ALIGNMENT_LEFT, width := -1.0) -> void:
	_font().draw_string(get_canvas_item(), pos, s, align, width, size, col)

func _rbox(r: Rect2, col: Color, radius := 6.0) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = col
	sb.set_corner_radius_all(int(radius))
	draw_style_box(sb, r)

func _draw() -> void:
	if boot == null or boot.players.is_empty():
		return
	var vp := size
	_scorebug()
	_banner(vp)
	_power(vp)
	_minimap(vp)

func _scorebug() -> void:
	var x := 18.0
	var y := 14.0
	_rbox(Rect2(x, y, 330, 38), Color(0.04, 0.06, 0.12, 0.88))
	_rbox(Rect2(x, y, 8, 38), boot.home_cols[0], 3)
	_rbox(Rect2(x + 322, y, 8, 38), boot.away_cols[0], 3)
	_text(Vector2(x + 16, y + 26), "HAR", 20, Color.WHITE)
	_rbox(Rect2(x + 76, y + 5, 36, 28), Color(1, 1, 1, 0.94), 4)
	_text(Vector2(x + 76, y + 27), str(boot.score[0]), 22, Color("#0b1220"), HORIZONTAL_ALIGNMENT_CENTER, 36)
	_rbox(Rect2(x + 118, y + 5, 36, 28), Color(1, 1, 1, 0.94), 4)
	_text(Vector2(x + 118, y + 27), str(boot.score[1]), 22, Color("#0b1220"), HORIZONTAL_ALIGNMENT_CENTER, 36)
	_text(Vector2(x + 164, y + 26), "NOR", 20, Color.WHITE)
	var clk := "%02d:%02d" % [int(boot.clock / 60.0), int(boot.clock) % 60]
	_rbox(Rect2(x + 236, y + 5, 78, 28), Color(0.12, 0.16, 0.28, 1.0), 4)
	_text(Vector2(x + 236, y + 26), clk, 18, Color("#ffd166"), HORIZONTAL_ALIGNMENT_CENTER, 78)
	var sub: String = boot.clock_lbl.text.get_slice("·", 1).strip_edges() if boot.clock_lbl.text.contains("·") else ""
	if sub != "":
		_text(Vector2(x + 2, y + 56), sub, 12, Color(1, 1, 1, 0.7))

func _banner(vp: Vector2) -> void:
	if banner_time <= 0.0:
		return
	var a := clampf(banner_time / 0.4, 0.0, 1.0) * clampf((2.4 - banner_time) / 0.18 + 0.2, 0.0, 1.0)
	var slide := (1.0 - clampf((banner_time_max() - banner_time) / 0.25, 0.0, 1.0)) * -60.0
	var w := 420.0
	var r := Rect2((vp.x - w) * 0.5 + slide, 74, w, 54)
	_rbox(r, Color(0.04, 0.06, 0.12, 0.86 * a))
	_rbox(Rect2(r.position.x, r.position.y, 8, r.size.y), Color(banner_col, a), 3)
	_text(Vector2(r.position.x, r.position.y + 39), banner_text, 34, Color(banner_col, a), HORIZONTAL_ALIGNMENT_CENTER, w)

func banner_time_max() -> float:
	return 2.2 if banner_text == "GOAL!" else 1.4

func _power(vp: Vector2) -> void:
	var c: float = boot.charge
	if c <= 0.01:
		return
	var w := 260.0
	var r := Rect2((vp.x - w) * 0.5, vp.y - 92, w, 14)
	_rbox(r, Color(0, 0, 0, 0.6), 7)
	var col := Color("#2bdb85").lerp(Color("#ff4d4d"), clampf((c - 0.6) / 0.4, 0.0, 1.0))
	_rbox(Rect2(r.position, Vector2(w * c, r.size.y)), col, 7)
	_text(Vector2(r.position.x, r.position.y - 6), "POWER", 12, Color(1, 1, 1, 0.8), HORIZONTAL_ALIGNMENT_CENTER, w)

func _minimap(vp: Vector2) -> void:
	var w := 168.0
	var h: float = w * (boot.HALF_W / boot.HALF_L)
	var o := Vector2(vp.x - w - 18.0, vp.y - h - 50.0)
	_rbox(Rect2(o - Vector2(4, 4), Vector2(w + 8, h + 8)), Color(0.04, 0.06, 0.12, 0.7))
	_rbox(Rect2(o, Vector2(w, h)), Color(0.1, 0.35, 0.16, 0.85), 2)
	draw_rect(Rect2(o, Vector2(w, h)), Color(1, 1, 1, 0.5), false, 1.0)
	draw_line(o + Vector2(w * 0.5, 0), o + Vector2(w * 0.5, h), Color(1, 1, 1, 0.5), 1.0)
	draw_arc(o + Vector2(w * 0.5, h * 0.5), h * 0.14, 0, TAU, 20, Color(1, 1, 1, 0.5), 1.0)
	for p in boot.players:
		var q: Vector2 = o + Vector2((p["pos"].x / boot.HALF_L * 0.5 + 0.5) * w, (p["pos"].z / boot.HALF_W * 0.5 + 0.5) * h)
		var col: Color = boot.home_cols[0] if p["team"] == 0 else boot.away_cols[0]
		draw_circle(q, 3.0, col)
	for hm in boot.humans:
		var pp: Dictionary = boot.players[hm["ctrl"]]
		var qq: Vector2 = o + Vector2((pp["pos"].x / boot.HALF_L * 0.5 + 0.5) * w, (pp["pos"].z / boot.HALF_W * 0.5 + 0.5) * h)
		draw_arc(qq, 5.0, 0, TAU, 14, Color.WHITE, 1.5)
	var bq: Vector2 = o + Vector2((boot.ball["pos"].x / boot.HALF_L * 0.5 + 0.5) * w, (boot.ball["pos"].z / boot.HALF_W * 0.5 + 0.5) * h)
	draw_circle(bq, 2.5, Color.WHITE)
