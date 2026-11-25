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

;; A warning when the catalog asks for a newer toolkit (settings.min_toolkit_version), or nil.
(defun il-toolkit-outdated (catalog / minimum)
  (setq minimum (il-jp catalog '("settings" "min_toolkit_version")))
  (if (and minimum (/= (il-str minimum) "") (il-version< *il-version* (il-str minimum)))
    (strcat "This CAD toolkit is " *il-version* "; the catalog needs " (il-str minimum)
            " or newer. Download the current toolkit from the portal Resources page")
  )
)

;; --- Linear fixture styles -------------------------------------------------------------------------
;; A linear template's "linear" object is the portal linear configurator's cascade, precomputed by the
;; portal: LED package, environment, CCT and lens narrow the buildable combos; each combo lists the
;; delivered outputs (lm/ft) the lens allows. The portal picks the tape from the output on import.

;; The combos matching the choices made so far (a nil choice matches anything).
(defun il-linear-combos (linear package environment cct lens / result)
  (foreach combo (il-items (il-j linear "combos"))
    (if (and (or (null package) (= (il-j combo "led_package") package))
             (or (null environment) (= (il-j combo "environment") environment))
             (or (null cct) (= (il-j combo "cct") cct))
             (or (null lens) (= (il-j combo "lens") lens)))
      (setq result (cons combo result))
    )
  )
  (reverse result)
)

;; The entries of LIST-KEY ("led_packages", "environments", "ccts", "lenses") some combo still
;; matching the earlier choices uses at COMBO-KEY, in catalog order.
(defun il-linear-choices (linear list-key combo-key package environment cct / combos)
  (setq combos (il-linear-combos linear package environment cct nil))
  (vl-remove-if-not
    '(lambda (entry) (vl-some '(lambda (combo) (= (il-j combo combo-key) (il-j entry "value"))) combos))
    (il-items (il-j linear list-key))
  )
)

;; The delivered outputs (lm/ft) of one full combination, as {value, label} entries.
(defun il-linear-outputs (linear package environment cct lens)
  (mapcar '(lambda (value) (il-obj (list (cons "value" value) (cons "label" (strcat (il-num->str value 0) " lm/ft")))))
          (il-items (il-j (car (il-linear-combos linear package environment cct lens)) "outputs")))
)

;; A lens entry labelled with its light transmission, as the portal shows it.
(defun il-linear-lens-entry (entry)
  (il-jset entry "label"
    (strcat (il-str (il-j entry "label"))
            (if (il-j entry "transmission_pct") (strcat " (" (il-num->str (il-j entry "transmission_pct") 1) "% transmission)") "")))
)

;; The run style a set of linear CHOICES makes: (("package" . v) ("environment" . v) ("cct" . v)
;; ("lens" . v) ("output" . lm/ft) ("mounting" . v) ("finish" . v) ("feed_type" . v)
;; ("feed_direction" . v)). Selections use the portal configurator's own keys, so the import builds it
;; exactly as a fixture configured in the portal; the feed defaults go on the style's segments.
(defun il-linear-style (template choices label / selections feed)
  (setq selections (list (cons "fixture_template_code" (il-j template "code"))))
  (foreach pair '(("package" . "led_package_code") ("environment" . "environment_rating_code") ("cct" . "cct_code")
                  ("lens" . "lens_appearance_code") ("mounting" . "mounting_method_code") ("finish" . "finish_code"))
    (if (il-get (car pair) choices) (setq selections (append selections (list (cons (cdr pair) (il-get (car pair) choices))))))
  )
  (if (il-get "output" choices) (setq selections (append selections (list (cons "delivered_output_value" (il-get "output" choices))))))
  (foreach pair '(("feed_type" . "start_power_feed_type") ("feed_direction" . "start_feed_direction")
                  ("feed_type" . "end_power_feed_type") ("feed_direction" . "end_feed_direction"))
    (if (il-get (car pair) choices) (setq feed (append feed (list (cons (cdr pair) (il-get (car pair) choices))))))
  )
  (il-obj (append (list (cons "id" (strcat "custom:" label)) (cons "label" label) (cons "family" "Linear Fixture")
                        (cons "template" (il-j template "code")) (cons "selections" (il-obj selections)))
                  (if feed (list (cons "segments" (il-arr (list (il-obj feed))))))))
)

;; The default name of a linear style: template, CCT, output and lens.
(defun il-linear-style-name (template choices)
  (il-trim (strcat (il-str (il-j template "code")) " " (il-str (il-get "cct" choices)) " "
                   (if (il-get "output" choices) (strcat (il-num->str (il-get "output" choices) 0) "lm") "") " "
                   (il-str (il-get "lens" choices))))
)
