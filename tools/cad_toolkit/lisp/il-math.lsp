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
