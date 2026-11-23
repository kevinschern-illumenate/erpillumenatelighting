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

;; The variant a style draws with (nil for linear fixtures, whose tape the configurator picks). A
;; custom style's is made from its own numbers (il-custom-variant). Every hint and check asks here.
(defun il-style-variant (catalog style / tape template)
  (if (il-custom-p style)
    (il-custom-variant style)
    (progn
      (setq tape (il-style-tape style))
      (if (and tape (il-tape-family-p (il-j tape "family")))
        (if (setq template (il-cat-template catalog (il-j tape "family") (il-j tape "template")))
          (il-cat-variant template (il-j tape "selections"))
        )
      )
    )
  )
)

;; The profile a style draws: the kit's or the linear template's default profile.
(defun il-style-profile (catalog style / template)
  (if (setq template (il-cat-template catalog (il-j style "family") (il-j style "template")))
    (if (il-j template "profile") (il-cat-profile catalog (il-j template "profile")))
  )
)

;; A short label for a style: its own label, else family and template. Custom styles say so.
(defun il-style-label (style)
  (cond
    ((il-custom-p style) (strcat (il-custom-label style) " (custom)"))
    ((il-j style "label"))
    ((il-j style "preset"))
    (T (strcat (il-j style "template") " " (il-j style "family")))
  )
)

;; What a style is: its family, or for a custom style the family it was defined as.
(defun il-style-family (style)
  (if (il-custom-p style) (il-str (il-j (il-j style "custom") "family")) (il-j style "family"))
)

;; --- Custom styles ------------------------------------------------------------------------------
;; A style the user defines in CAD without a catalog template (ILSTYLE "Custom style"): id
;; "custom:<CODE>", family "Custom", template CODE, no selections, and a "custom" object with code,
;; label, family, color and the optional w_per_ft, voltage_v, cut_in, max_run_ft, part_number, notes
;; (the ilq/2 custom style). Its numbers drive the hints and checks; on import it is mapped to a preset,
;; or becomes a custom schedule line for Sales to price.

(setq *il-custom-families* '("LED Tape" "COB Tape" "LED Neon" "Linear Fixture" "Extrusion Kit" "Other"))

;; Default colours (AutoCAD colour index) by family; they keep off red, yellow and green, which mark
;; ILCHECK states.
(setq *il-custom-colors*
  '(("LED Tape" . 30) ("COB Tape" . 40) ("LED Neon" . 6) ("Linear Fixture" . 4) ("Extrusion Kit" . 5) ("Other" . 7)))

;; The numbers a custom style may carry, as the ilq/2 schema bounds them: (key low high low-allowed).
(setq *il-custom-numbers*
  '(("w_per_ft" 0 1000 T) ("voltage_v" 0 1000 nil) ("cut_in" 0 1000 nil) ("max_run_ft" 0 10000 nil)))

;; Free text a custom style may carry, with its longest length.
(setq *il-custom-texts* '(("part_number" . 140) ("notes" . 1000)))

(defun il-custom-p (style) (= (il-j style "family") "Custom"))

(defun il-custom-label (style / label)
  (setq label (il-j (il-j style "custom") "label"))
  (cond
    ((and label (/= (il-trim label) "")) label)
    ((il-j style "label"))
    (T (il-str (il-j style "template")))
  )
)

(defun il-custom-default-color (family / color)
  (if (setq color (cdr (assoc family *il-custom-colors*))) color 7)
)

(defun il-custom-color-ok (value)
  (and (numberp value) (= value (fix value)) (>= value 1) (<= value 255))
)

;; True when VALUE is a number the schema accepts for KEY (one of *il-custom-numbers*).
(defun il-custom-number-ok (key value / row)
  (setq row (assoc key *il-custom-numbers*))
  (and row (numberp value) (<= value (caddr row))
       (if (cadddr row) (>= value (cadr row)) (> value (cadr row))))
)

;; A custom style code from LABEL: upper-case letters and digits, any other run of characters one "-",
;; at most 24 characters, starting and ending with a letter or digit ("Cove 24V 4.4 W/ft" -> "COVE-24V-4-4-W-FT").
(defun il-custom-slug (label / text index char code out)
  (setq text (strcase (il-trim label)) index 1 out "")
  (while (<= index (strlen text))
    (setq char (substr text index 1) code (ascii char) index (1+ index))
    (cond
      ((or (< 47 code 58) (< 64 code 91)) (setq out (strcat out char)))
      ((and (/= out "") (/= (substr out (strlen out) 1) "-")) (setq out (strcat out "-")))
    )
  )
  (setq out (vl-string-right-trim "-" (substr out 1 24)))
  (if (= out "") "CUSTOM" out)
)

;; The codes STYLES (the drawing's) already use: custom styles' codes and every "custom:<x>" id.
(defun il-custom-codes (styles / codes id)
  (foreach style styles
    (setq id (il-str (il-j style "id")))
    (if (il-starts-with id "custom:") (setq codes (cons (substr id 8) codes)))
    (if (il-custom-p style) (setq codes (cons (il-str (il-j style "template")) codes)))
  )
  codes
)

;; A new style's code: LABEL's slug, made unique among STYLES ("COVE", "COVE-2", ...).
(defun il-custom-new-code (label styles)
  (il-unique-id (il-custom-slug label) (il-custom-codes styles) 24)
)

;; The custom style CODE from ANSWERS (("label" . text) ("family" . f) ("color" . n) ("w_per_ft" . x) ...).
;; A blank label is the code; an unknown family is "Other"; a missing or bad colour is the family's;
;; numbers out of the schema's range and blank texts are left out; texts are cut to the schema's length.
(defun il-custom-style (code answers / family label value pairs)
  (setq family (il-get "family" answers))
  (if (not (member family *il-custom-families*)) (setq family "Other"))
  (setq label (substr (il-trim (il-get "label" answers)) 1 140))
  (if (= label "") (setq label code))
  (setq value (il-get "color" answers))
  (setq pairs (list (cons "code" code) (cons "label" label) (cons "family" family)
                    (cons "color" (if (il-custom-color-ok value) (fix value) (il-custom-default-color family)))))
  (foreach row *il-custom-numbers*
    (setq value (il-get (car row) answers))
    (if (il-custom-number-ok (car row) value) (setq pairs (append pairs (list (cons (car row) value)))))
  )
  (foreach row *il-custom-texts*
    (setq value (il-trim (il-get (car row) answers)))
    (if (/= value "") (setq pairs (append pairs (list (cons (car row) (substr value 1 (cdr row)))))))
  )
  (il-obj (list (cons "id" (strcat "custom:" code)) (cons "label" label) (cons "family" "Custom")
                (cons "template" code) (cons "selections" (il-obj nil)) (cons "custom" (il-obj pairs))))
)

;; The variant a custom style draws with: its W/ft, its cut increment in mm (free cut without one) and
;; its max run as the voltage-drop max run (il-run-split still applies the 85 W per run rule).
(defun il-custom-variant (style / custom cut)
  (setq custom (il-j style "custom") cut (il-j custom "cut_in"))
  (if (not (il-custom-number-ok "cut_in" cut)) (setq cut nil))
  (il-obj
    (list
      (cons "id" (strcat "custom:" (il-str (il-j style "template"))))
      (cons "w_per_ft" (if (il-custom-number-ok "w_per_ft" (il-j custom "w_per_ft")) (il-j custom "w_per_ft")))
      (cons "cut_mm" (if cut (* cut *il-mm-per-in*)))
      (cons "free_cut" (il-bool (null cut)))
      (cons "max_run_vd_ft" (if (il-custom-number-ok "max_run_ft" (il-j custom "max_run_ft")) (il-j custom "max_run_ft")))
      ;; The user's own max run always wins, over the 85 W per run rule too.
      (cons "max_run_override_ft" (if (il-custom-number-ok "max_run_ft" (il-j custom "max_run_ft")) (il-j custom "max_run_ft")))
      (cons "voltage_v" (if (il-custom-number-ok "voltage_v" (il-j custom "voltage_v")) (il-j custom "voltage_v")))
    )
  )
)

;; ILCHECK's note on a custom run (info: it never blocks).
(defun il-custom-issue-text (style)
  (strcat "Uses custom style " (il-custom-label style) " (" (il-str (il-j style "template"))
          "); the import maps it to a preset, or adds a custom line for Sales to price")
)

;; The colour (AutoCAD colour index) of a run of STYLE in STATE ("error", "warning", "imported", "ok"):
;; red and yellow for problems; else a custom style's own colour, green, or ByLayer once imported.
(defun il-run-color (state style / color)
  (if (il-custom-p style)
    (setq color (il-j (il-j style "custom") "color")
          color (if (il-custom-color-ok color) (fix color) (il-custom-default-color (il-style-family style))))
  )
  (cond
    ((= state "error") 1)
    ((= state "warning") 2)
    (color color)
    ((= state "imported") 256)
    (T 3)
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
