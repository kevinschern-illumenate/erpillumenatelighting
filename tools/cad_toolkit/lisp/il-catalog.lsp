;;; il-catalog.lsp -- ilLumenate CAD toolkit: the CAD catalog (cad-catalog/1) and its lookups.
;;;
;;; The catalog is a file the dealer downloads from the portal (no network calls from AutoCAD). It
;;; holds templates, variants, profiles and run styles, never prices. Pure: CI runs it.

(setq *il-catalog* nil *il-catalog-path* nil)

(defun il-catalog-read (path / catalog)
  (setq catalog (il-json-read-file path))
  (cond
    ((null catalog) nil)
    ((/= (il-j catalog "schema") "cad-catalog/1")
      (setq *il-jr-error* "This file is not an ilLumenate CAD catalog (cad-catalog/1)")
      nil
    )
    (T catalog)
  )
)

(defun il-tape-family-p (family)
  (member family '("LED Tape" "COB Tape" "LED Neon"))
)

;; The template FAMILY/CODE offers, as its catalog object, or nil when the catalog does not offer it.
(defun il-cat-template (catalog family code / found section)
  (setq section
    (cond
      ((il-tape-family-p family) "templates")
      ((= family "Linear Fixture") "fixture_templates")
      ((= family "Extrusion Kit") "kit_templates")
    )
  )
  (if section
    (foreach item (il-items (il-j catalog section))
      (if (and (null found) (= (il-j item "code") code)
               (or (/= section "templates") (= (il-j item "family") family)))
        (setq found item)
      )
    )
  )
  found
)

(defun il-cat-profile (catalog code / found)
  (foreach item (il-items (il-j catalog "profiles"))
    (if (and (null found) (= (il-j item "code") code)) (setq found item))
  )
  found
)

(defun il-cat-style (catalog id / found)
  (foreach item (il-items (il-j catalog "styles"))
    (if (and (null found) (= (il-j item "id") id)) (setq found item))
  )
  found
)

(defun il-cat-option (template key / found)
  (foreach option (il-items (il-j template "options"))
    (if (and (null found) (= (il-j option "key") key)) (setq found option))
  )
  found
)

;; The variant matching SELECTIONS (environment, CCT, output); the template default otherwise.
(defun il-cat-variant (template selections / best best-score score default)
  (setq best-score -1)
  (foreach variant (il-items (il-j template "variants"))
    (if (= (il-j variant "id") (il-j template "default_variant")) (setq default variant))
    (setq score 0)
    (foreach key '("environment_rating" "cct" "output_level")
      (cond
        ((null (il-j selections key)))
        ((null (il-j variant key)))
        ((= (il-j selections key) (il-j variant key)) (setq score (1+ score)))
        (T (setq score -100))
      )
    )
    (if (> score best-score) (setq best variant best-score score))
  )
  (if (>= best-score 0) best default)
)

;; The tape style that carries the light: the style itself, or a kit style's tape.
(defun il-style-tape (style)
  (if (= (il-j style "family") "Extrusion Kit") (il-j style "tape") style)
)

;; The variant a style draws with (nil for linear fixtures, whose tape the configurator picks).
(defun il-style-variant (catalog style / tape template)
  (setq tape (il-style-tape style))
  (if (and tape (il-tape-family-p (il-j tape "family")))
    (if (setq template (il-cat-template catalog (il-j tape "family") (il-j tape "template")))
      (il-cat-variant template (il-j tape "selections"))
    )
  )
)

;; The profile a style draws: the kit's or the linear template's default profile.
(defun il-style-profile (catalog style / template)
  (if (setq template (il-cat-template catalog (il-j style "family") (il-j style "template")))
    (if (il-j template "profile") (il-cat-profile catalog (il-j template "profile")))
  )
)

;; A short label for a style: its own label, else family and template.
(defun il-style-label (style)
  (cond
    ((il-j style "label"))
    ((il-j style "preset"))
    (T (strcat (il-j style "template") " " (il-j style "family")))
  )
)

;; Days between two "YYYY-MM-DD..." dates (approximate: 365-day years, 30.4-day months are fine
;; for a 30-day staleness warning).
(defun il-day-number (text)
  (+ (* 365.25 (atoi (substr text 1 4))) (* 30.44 (atoi (substr text 6 2))) (atoi (substr text 9 2)))
)

(defun il-days-between (from to)
  (fix (- (il-day-number to) (il-day-number from)))
)

;; A staleness warning, or nil. TODAY is "YYYY-MM-DD".
(defun il-catalog-stale (catalog today / days limit)
  (setq limit (il-jp catalog '("settings" "stale_days")))
  (if (null limit) (setq limit 30))
  (if (il-j catalog "generated_at")
    (progn
      (setq days (il-days-between (il-j catalog "generated_at") today))
      (if (> days limit)
        (strcat "The CAD catalog is " (itoa days) " days old; download the current one from the portal")
      )
    )
  )
)
