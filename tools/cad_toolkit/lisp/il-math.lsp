;;; il-math.lsp -- ilLumenate CAD toolkit: the hint math (draw-to-quote plan 1.7).
;;;
;;; The toolkit only shows hints; the configurators decide on import. These mirror, one for one,
;;; tools/cad_toolkit/reference/cad_subset.py and the server rules it is tested against:
;;;   cut snap   -- configuration_contract.whole_increments as tape_neon_configurator applies it
;;;   max run    -- tape_neon_configurator._compute_run_split (85 W per run, voltage-drop run)
;;;   PSU load   -- watts against rated W x usable_load_factor (a provisional tag, never sizing)
;;;   path       -- polyline length with bulges and its smallest arc radius (bend check)
;;; tools/system_designer/fixtures/cad/lisp-subset.json holds the shared golden cases.

(setq *il-mm-per-in* 25.4 *il-mm-per-ft* 304.8 *il-max-watts-per-run* 85.0)

(defun il-whole-increments (size increment)
  (il-floor (+ (/ (float size) increment) 1e-9))
)

;; One segment: ((mfg_in . x) (increments . n) (diff_in . d)).
(defun il-cut-snap (length-in cut-mm free-cut / requested increments mfg)
  (setq requested (* length-in *il-mm-per-in*))
  (if (or free-cut (null cut-mm) (<= cut-mm 0) (<= requested 0))
    (list (cons "mfg_in" (il-round-py length-in 4)) (cons "increments" nil) (cons "diff_in" 0.0))
    (progn
      (setq increments (max 1 (il-whole-increments requested cut-mm)))
      (setq mfg (* increments cut-mm))
      (list
        (cons "mfg_in" (il-round-py (/ mfg *il-mm-per-in*) 4))
        (cons "increments" increments)
        (cons "diff_in" (il-round-py (/ (- requested mfg) *il-mm-per-in*) 4))
      )
    )
  )
)

;; The configurator's effective max run in feet; nil means no limit.
(defun il-max-run-ft (w-per-ft vd-ft override-ft / by-watts)
  (cond
    ((and override-ft (> override-ft 0)) (float override-ft))
    (T
      (setq by-watts (if (and w-per-ft (> w-per-ft 0)) (/ *il-max-watts-per-run* w-per-ft)))
      (cond
        ((and vd-ft (> vd-ft 0) by-watts) (min by-watts (float vd-ft)))
        ((and vd-ft (> vd-ft 0)) (float vd-ft))
        (T by-watts)
      )
    )
  )
)

;; ((max_run_ft . f) (pct_of_max . p) (runs_count . n) (runs_in . (a b ...))).
(defun il-run-split (length-in w-per-ft cut-mm free-cut vd-ft override-ft
                     / length-mm effective max-mm count increment total base extra index runs)
  (setq length-mm (* length-in *il-mm-per-in*)
        effective (il-max-run-ft w-per-ft vd-ft override-ft))
  (setq max-mm (if effective (* effective *il-mm-per-ft*)))
  (setq count
    (if (and max-mm (> length-mm max-mm)) (il-ceil (/ length-mm max-mm)) 1))
  (setq increment (if (and (not free-cut) cut-mm (> cut-mm 0)) cut-mm 0))
  (cond
    ((= count 1) (setq runs (list length-mm)))
    ((> increment 0)
      (setq total (il-round-even (/ length-mm increment))
            base (/ total count)
            extra (rem total count)
            index 0)
      (repeat count
        (setq runs (cons (* (+ base (if (< index extra) 1 0)) increment) runs) index (1+ index))
      )
      (setq runs (reverse runs))
    )
    (T (repeat count (setq runs (cons (/ length-mm count) runs))))
  )
  (list
    (cons "max_run_ft" (if effective (il-round-py effective 2)))
    (cons "pct_of_max" (if effective (il-round-py (/ (* 100.0 (/ length-mm *il-mm-per-ft*)) effective) 1)))
    (cons "runs_count" count)
    (cons "runs_in" (mapcar '(lambda (mm) (il-round-py (/ mm *il-mm-per-in*) 2)) runs))
  )
)

(defun il-run-watts (length-in w-per-ft)
  (il-round-py (* (/ length-in 12.0) w-per-ft) 2)
)

;; ((total_w . t) (usable_w . u) (pct_of_usable . p) (over . flag)).
(defun il-psu-load (loads rated-w factor / total usable)
  (setq total (il-sum loads) usable (* rated-w (if factor factor 1.0)))
  (list
    (cons "total_w" (il-round-py total 2))
    (cons "usable_w" (il-round-py usable 2))
    (cons "pct_of_usable" (if (> usable 0) (il-round-py (/ (* 100.0 total) usable) 1)))
    (cons "over" (> total usable))
  )
)

;; VERTICES is ((x y bulge) ...): ((length_in . l) (min_arc_radius_in . r-or-nil)).
(defun il-path-length (vertices closed / points total smallest start end chord bulge sweep radius)
  (setq points vertices total 0.0)
  (if (and closed points) (setq points (append points (list (car points)))))
  (while (cdr points)
    (setq start (car points) end (cadr points) points (cdr points))
    (setq chord (distance (list (car start) (cadr start)) (list (car end) (cadr end))))
    (setq bulge (if (caddr start) (caddr start) 0.0))
    (if (or (equal bulge 0.0 1e-12) (= chord 0))
      (setq total (+ total chord))
      (progn
        (setq sweep (* 4 (atan (abs bulge))))
        (setq radius (/ chord (* 2 (sin (/ sweep 2)))))
        (setq total (+ total (* radius sweep)))
        (setq smallest (if smallest (min smallest radius) radius))
      )
    )
  )
  (list
    (cons "length_in" (il-round-py total 4))
    (cons "min_arc_radius_in" (if smallest (il-round-py smallest 4)))
  )
)

;; Split VERTICES at the vertex indexes in BREAKS (jumpers): a list of vertex lists, one per segment.
(defun il-split-vertices (vertices breaks / segments current index)
  (setq index 0)
  (foreach vertex vertices
    (setq current (cons vertex current))
    (if (and (member index breaks) (> index 0) (< index (1- (length vertices))))
      (setq segments (cons (reverse current) segments)
            current (list (list (car vertex) (cadr vertex) (caddr vertex))))
    )
    (setq index (1+ index))
  )
  (reverse (cons (reverse current) segments))
)

;; --- Polyline editing: ILJUMPER, ILFEED, tag placement -----------------------------------------

(setq *il-two-pi* (* 8.0 (atan 1.0)))

(defun il-xy (point) (list (float (car point)) (float (cadr point))))

(defun il-bulge (vertex) (if (numberp (caddr vertex)) (caddr vertex) 0.0))

;; The arc of segment P0 -> P1 with BULGE: (center radius start-angle sweep), nil when straight.
;; A positive bulge turns counterclockwise; its center lies left of the chord.
(defun il-bulge-arc (p0 p1 bulge / dx dy chord offset center)
  (setq dx (- (car p1) (car p0)) dy (- (cadr p1) (cadr p0)) chord (sqrt (+ (* dx dx) (* dy dy))))
  (if (and (not (equal bulge 0.0 1e-12)) (> chord 0))
    (progn
      (setq offset (/ (* chord (- 1.0 (* bulge bulge))) (* 4.0 bulge)))
      (setq center (list (- (/ (+ (car p0) (car p1)) 2.0) (* offset (/ dy chord)))
                         (+ (/ (+ (cadr p0) (cadr p1)) 2.0) (* offset (/ dx chord)))))
      (list center (/ (* chord (+ 1.0 (* bulge bulge))) (* 4.0 (abs bulge)))
            (atan (- (cadr p0) (cadr center)) (- (car p0) (car center))) (* 4.0 (atan bulge)))
    )
  )
)

(defun il-arc-point (arc angle-at)
  (list (+ (car (car arc)) (* (cadr arc) (cos angle-at))) (+ (cadr (car arc)) (* (cadr arc) (sin angle-at))))
)

(defun il-segment-length (p0 p1 bulge / arc)
  (if (setq arc (il-bulge-arc p0 p1 bulge)) (* (cadr arc) (abs (cadddr arc))) (distance (il-xy p0) (il-xy p1)))
)

;; The point U (0..1) of the way along segment P0 -> P1.
(defun il-segment-point (p0 p1 bulge u / arc)
  (if (setq arc (il-bulge-arc p0 p1 bulge))
    (il-arc-point arc (+ (caddr arc) (* u (cadddr arc))))
    (list (+ (car p0) (* u (- (car p1) (car p0)))) (+ (cadr p0) (* u (- (cadr p1) (cadr p0)))))
  )
)

;; The point FRACTION (0..1) of the way along open VERTICES ((x y bulge) ...), as (x y 0.0).
(defun il-path-point (vertices fraction / lengths total target walked points index result)
  (setq points vertices)
  (while (cdr points)
    (setq lengths (cons (il-segment-length (car points) (cadr points) (il-bulge (car points))) lengths) points (cdr points))
  )
  (setq lengths (reverse lengths) total (apply '+ (cons 0.0 lengths)) target (* fraction total) walked 0.0 index 0)
  (if (or (null lengths) (<= total 0)) (setq result (il-xy (car vertices))))
  (foreach size lengths
    (if (and (null result) (or (>= (+ walked size) target) (= index (1- (length lengths)))))
      (setq result (il-segment-point (nth index vertices) (nth (1+ index) vertices) (il-bulge (nth index vertices))
                                     (if (> size 0) (min 1.0 (max 0.0 (/ (- target walked) size))) 0.0)))
    )
    (setq walked (+ walked size) index (1+ index))
  )
  (list (car result) (cadr result) 0.0)
)

;; The closest point of segment P0 -> P1 to POINT: (u point distance), U being 0..1 along it.
(defun il-segment-nearest (p0 p1 bulge point / arc dx dy size u along swept)
  (if (setq arc (il-bulge-arc p0 p1 bulge))
    (progn
      (setq along (atan (- (cadr point) (cadr (car arc))) (- (car point) (car (car arc)))))
      (setq swept (rem (- along (caddr arc)) *il-two-pi*))
      (if (> (cadddr arc) 0)
        (if (< swept 0) (setq swept (+ swept *il-two-pi*)))
        (if (> swept 0) (setq swept (- swept *il-two-pi*)))
      )
      (if (<= (abs swept) (abs (cadddr arc)))
        (setq u (/ swept (cadddr arc)))
        (setq u (if (< (distance (il-xy point) (il-xy p0)) (distance (il-xy point) (il-xy p1))) 0.0 1.0))
      )
    )
    (progn
      (setq dx (- (car p1) (car p0)) dy (- (cadr p1) (cadr p0)) size (+ (* dx dx) (* dy dy)))
      (setq u (if (> size 0) (/ (+ (* (- (car point) (car p0)) dx) (* (- (cadr point) (cadr p0)) dy)) size) 0.0))
      (setq u (min 1.0 (max 0.0 u)))
    )
  )
  (setq along (il-segment-point p0 p1 bulge u))
  (list u along (distance (il-xy point) along))
)

;; Where a picked POINT lands on open VERTICES: ("vertex" index) when it is within TOLERANCE of a vertex
;; (or its nearest point on the run is), else ("split" segment-index u point) to add a vertex exactly
;; at the nearest point on the run. TOLERANCE is small: snapped points land where they were snapped.
(defun il-jumper-target (vertices point tolerance / best best-d index d near best-seg)
  (setq index 0)
  (foreach vertex vertices
    (setq d (distance (il-xy vertex) (il-xy point)))
    (if (or (null best-d) (< d best-d)) (setq best index best-d d))
    (setq index (1+ index))
  )
  (setq index 0)
  (while (< index (1- (length vertices)))
    (setq near (il-segment-nearest (nth index vertices) (nth (1+ index) vertices) (il-bulge (nth index vertices)) point))
    (if (or (null best-seg) (< (caddr near) (caddr (cdr best-seg)))) (setq best-seg (cons index near)))
    (setq index (1+ index))
  )
  (cond
    ((or (null best-seg) (<= best-d tolerance)) (list "vertex" best))
    ((<= (distance (il-xy (caddr best-seg)) (il-xy (nth (car best-seg) vertices))) tolerance) (list "vertex" (car best-seg)))
    ((<= (distance (il-xy (caddr best-seg)) (il-xy (nth (1+ (car best-seg)) vertices))) tolerance) (list "vertex" (1+ (car best-seg))))
    (T (list "split" (car best-seg) (cadr best-seg) (caddr best-seg)))
  )
)

;; How far POINT is from the path of VERTICES (closed paths include the closing side).
(defun il-distance-to-path (vertices closed point / points best near)
  (setq points (if closed (append vertices (list (car vertices))) vertices))
  (if (null (cdr points))
    (if points (distance (il-xy (car points)) (il-xy point)))
    (progn
      (while (cdr points)
        (setq near (il-segment-nearest (car points) (cadr points) (il-bulge (car points)) point))
        (if (or (null best) (< (caddr near) best)) (setq best (caddr near)))
        (setq points (cdr points))
      )
      best
    )
  )
)

(defun il-tan (x) (/ (sin x) (cos x)))

;; VERTICES with a new vertex at U along segment INDEX (an arc splits into two arcs).
(defun il-insert-vertex (vertices index u / arc result i point)
  (setq arc (il-bulge-arc (nth index vertices) (nth (1+ index) vertices) (il-bulge (nth index vertices))))
  (setq point (il-segment-point (nth index vertices) (nth (1+ index) vertices) (il-bulge (nth index vertices)) u) i 0)
  (foreach vertex vertices
    (if (= i index)
      (setq result (cons (list (car point) (cadr point) (if arc (il-tan (/ (* (- 1.0 u) (cadddr arc)) 4.0)) 0.0))
                         (cons (list (car vertex) (cadr vertex) (if arc (il-tan (/ (* u (cadddr arc)) 4.0)) 0.0)) result)))
      (setq result (cons vertex result))
    )
    (setq i (1+ i))
  )
  (reverse result)
)

;; Break indexes after a vertex was added following INDEX.
(defun il-shift-breaks (breaks index)
  (mapcar '(lambda (b) (if (> b index) (1+ b) b)) breaks)
)

;; Open VERTICES drawn the other way: each segment keeps its arc (bulges flip sign and move along).
(defun il-reverse-vertices (vertices / reversed result index)
  (setq reversed (reverse vertices) index 0)
  (foreach vertex reversed
    (setq result (cons (list (car vertex) (cadr vertex)
                             (if (< index (1- (length reversed))) (- (il-bulge (nth (1+ index) reversed))) 0.0))
                       result)
          index (1+ index))
  )
  (reverse result)
)

(defun il-reverse-breaks (breaks count)
  (vl-sort (mapcar '(lambda (b) (- count 1 b)) breaks) '<)
)

;; Spans (segment indexes) after a vertex was added following segment INDEX: a split span is two.
(defun il-split-spans (spans index / result)
  (foreach s spans
    (cond
      ((< s index) (setq result (cons s result)))
      ((= s index) (setq result (cons (1+ s) (cons s result))))
      (T (setq result (cons (1+ s) result)))
    )
  )
  (reverse result)
)

;; Spans of open VERTICES (COUNT of them) drawn the other way.
(defun il-reverse-spans (spans count)
  (vl-sort (mapcar '(lambda (s) (- count 2 s)) spans) '<)
)

;; The segment of open VERTICES nearest POINT.
(defun il-nearest-segment (vertices point / index best best-d near)
  (setq index 0)
  (while (< index (1- (length vertices)))
    (setq near (il-segment-nearest (nth index vertices) (nth (1+ index) vertices) (il-bulge (nth index vertices)) point))
    (if (or (null best-d) (< (caddr near) best-d)) (setq best index best-d (caddr near)))
    (setq index (1+ index))
  )
  best
)

;; The run of consecutive SPANS that holds segment INDEX.
(defun il-span-group (spans index / low high result)
  (if (member index spans)
    (progn
      (setq low index high index)
      (while (member (1- low) spans) (setq low (1- low)))
      (while (member (1+ high) spans) (setq high (1+ high)))
      (while (<= low high) (setq result (cons low result) low (1+ low)))
      (reverse result)
    )
  )
)

;; The lit pieces of a run and what follows each: ((vertices jumper-p jumper-in) ...). BREAKS are
;; vertex indexes where a jumper of JUMPER-IN joins two pieces; SPANS are segment indexes drawn as
;; jumper cable, not tape, whose drawn length is that jumper's length. A span at either end of the
;; run joins nothing and is left out. A closed run is walked from its first vertex round to it.
(defun il-run-pieces (vertices closed breaks spans jumper-in / points count index items current gap result next after)
  (setq points (if (and closed vertices)
                 (append vertices (list (list (car (car vertices)) (cadr (car vertices)) 0.0)))
                 vertices))
  (setq count (length points) index 0 gap 0.0 current (list (car points)))
  (while (< index (1- count))
    (if (member index spans)
      (progn
        (if (cdr current) (setq items (cons (list "lit" (reverse current)) items)))
        (setq gap (+ gap (il-segment-length (nth index points) (nth (1+ index) points) (il-bulge (nth index points)))))
        (setq current (list (nth (1+ index) points)))
      )
      (progn
        (if (> gap 0) (setq items (cons (list "gap" gap) items) gap 0.0))
        (setq current (cons (nth (1+ index) points) current))
        (if (and (member (1+ index) breaks) (< (1+ index) (1- count)) (not (member (1+ index) spans)))
          (setq items (cons (list "break") (cons (list "lit" (reverse current)) items))
                current (list (nth (1+ index) points)))
        )
      )
    )
    (setq index (1+ index))
  )
  (if (cdr current) (setq items (cons (list "lit" (reverse current)) items)))
  (setq items (reverse items) index 0)
  (foreach item items
    (if (= (car item) "lit")
      (progn
        (setq next (nth (1+ index) items) after (nth (+ index 2) items))
        (setq result (cons (cond ((and next (= (car next) "break")) (list (cadr item) T jumper-in))
                                 ((and next (= (car next) "gap") after) (list (cadr item) T (il-round-py (cadr next) 2)))
                                 (T (list (cadr item) nil nil)))
                           result))
      )
    )
    (setq index (1+ index))
  )
  (reverse result)
)

;; --- Joining lines and arcs (ILCONVERT) ---------------------------------------------------------

;; An ARC (center, radius, start and end angle, counterclockwise) as two vertices with a bulge.
(defun il-arc-piece (center radius start end / sweep)
  (setq sweep (rem (- end start) *il-two-pi*))
  (if (<= sweep 0) (setq sweep (+ sweep *il-two-pi*)))
  (list (list (+ (car center) (* radius (cos start))) (+ (cadr center) (* radius (sin start))) (il-tan (/ sweep 4.0)))
        (list (+ (car center) (* radius (cos end))) (+ (cadr center) (* radius (sin end))) 0.0))
)

(defun il-butlast (items) (reverse (cdr (reverse items))))

(defun il-same-point (a b tolerance) (<= (distance (il-xy a) (il-xy b)) tolerance))

;; Join open PIECES (vertex lists) end to end where they meet within TOLERANCE, turning pieces round
;; as needed. Returns ((vertices . source-indexes) ...), one per chain.
(defun il-chain-pieces (pieces tolerance / left chains chain used grown index piece)
  (setq index 0)
  (foreach piece pieces (setq left (cons index left) index (1+ index)))
  (setq left (reverse left))
  (while left
    (setq chain (nth (car left) pieces) used (list (car left)) left (cdr left) grown T)
    (while grown
      (setq grown nil)
      (foreach index left
        (if (not grown)
          (progn
            (setq piece (nth index pieces))
            (cond
              ((il-same-point (last chain) (car piece) tolerance) (setq chain (append (il-butlast chain) piece) grown T))
              ((il-same-point (last chain) (last piece) tolerance) (setq chain (append (il-butlast chain) (il-reverse-vertices piece)) grown T))
              ((il-same-point (car chain) (last piece) tolerance) (setq chain (append (il-butlast piece) chain) grown T))
              ((il-same-point (car chain) (car piece) tolerance) (setq chain (append (il-butlast (il-reverse-vertices piece)) chain) grown T))
            )
            (if grown (setq used (cons index used) left (vl-remove index left)))
          )
        )
      )
    )
    (setq chains (cons (cons chain (reverse used)) chains))
  )
  (reverse chains)
)
