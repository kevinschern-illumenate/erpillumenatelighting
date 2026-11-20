;;; il-util.lsp -- ilLumenate CAD toolkit: pure helpers (strings, lists, numbers).
;;;
;;; No AutoCAD calls here, so tools/cad_toolkit/test/mini_lisp.py can run it in CI. Plain AutoLISP
;;; plus a few vl- string and list functions that full AutoCAD, LT 2024+ and Mac all provide
;;; (no vlax-/vla- ActiveX, no reactors).

(setq *il-version* "0.3.0")

;; --- Association lists ------------------------------------------------------------------------

(defun il-get (key alist / pair)
  (if (setq pair (assoc key alist)) (cdr pair))
)

(defun il-put (key value alist)
  (if (assoc key alist)
    (subst (cons key value) (assoc key alist) alist)
    (append alist (list (cons key value)))
  )
)

(defun il-drop (key alist / result)
  (foreach pair alist
    (if (not (equal (car pair) key)) (setq result (cons pair result)))
  )
  (reverse result)
)

;; --- Strings ----------------------------------------------------------------------------------

(defun il-str (value)
  (cond
    ((null value) "")
    ((= (type value) 'STR) value)
    ((= (type value) 'INT) (itoa value))
    ((= (type value) 'REAL) (il-num->str value 4))
    (T (vl-princ-to-string value))
  )
)

(defun il-trim (text)
  (vl-string-trim " \t\r\n" (il-str text))
)

(defun il-split (text sep / parts at size)
  (setq size (strlen sep))
  (while (setq at (vl-string-search sep text))
    (setq parts (cons (substr text 1 at) parts)
          text (substr text (+ at size 1)))
  )
  (reverse (cons text parts))
)

(defun il-join (items sep / result)
  (setq result "")
  (foreach item items
    (setq result (if (= result "") (il-str item) (strcat result sep (il-str item))))
  )
  result
)

(defun il-replace-all (text old new / at result size)
  (setq result "" size (strlen old))
  (while (setq at (vl-string-search old text))
    (setq result (strcat result (substr text 1 at) new)
          text (substr text (+ at size 1)))
  )
  (strcat result text)
)

(defun il-starts-with (text prefix)
  (and (>= (strlen text) (strlen prefix)) (= (substr text 1 (strlen prefix)) prefix))
)

(defun il-pad2 (number)
  (if (< number 10) (strcat "0" (itoa number)) (itoa number))
)

;; --- Numbers ----------------------------------------------------------------------------------

(defun il-floor (x / n)
  (setq n (fix x))
  (if (and (< x 0) (/= x n)) (1- n) n)
)

(defun il-ceil (x / n)
  (setq n (fix x))
  (if (and (> x 0) (/= x n)) (1+ n) n)
)

;; Round half away from zero to DIGITS decimals (display values).
(defun il-round (x digits / scale)
  (setq scale (expt 10.0 digits))
  (if (minusp x)
    (- (/ (il-floor (+ (* (- x) scale) 0.5)) scale))
    (/ (il-floor (+ (* x scale) 0.5)) scale)
  )
)

;; Round half to even to a whole number, like Python's round(): the configurator's equal split
;; (tape_neon_configurator._compute_run_split) uses it, so the hint must too.
(defun il-round-even (x / low diff)
  (setq low (il-floor x) diff (- x low))
  (cond
    ((< diff 0.5) low)
    ((> diff 0.5) (1+ low))
    ((= (rem low 2) 0) low)
    (T (1+ low))
  )
)

;; Python round(x, digits) for reporting (half to even on the scaled value, then back).
(defun il-round-py (x digits / scale scaled low diff)
  (setq scale (expt 10.0 digits) scaled (* x scale) low (il-floor scaled) diff (- scaled low))
  (cond
    ((< (abs (- diff 0.5)) 1e-9) (/ (il-round-even scaled) scale))
    (T (/ (il-floor (+ scaled 0.5)) scale))
  )
)

;; A number as text with at most DIGITS decimals and no trailing zeros ("12", "12.5").
(defun il-num->str (x digits / text)
  (if (= (type x) 'INT)
    (itoa x)
    (progn
      (setq text (rtos (il-round x digits) 2 digits))
      (if (vl-string-search "." text)
        (progn
          (setq text (vl-string-right-trim "0" text))
          (if (= (substr text (strlen text)) ".") (setq text (substr text 1 (1- (strlen text)))))
        )
      )
      (if (= text "-0") "0" text)
    )
  )
)

(defun il-number (value)
  (cond
    ((numberp value) value)
    ((and (= (type value) 'STR) (/= (il-trim value) "")) (atof value))
    (T nil)
  )
)

(defun il-sum (numbers / total)
  (setq total 0.0)
  (foreach n numbers (if (numberp n) (setq total (+ total n))))
  total
)
