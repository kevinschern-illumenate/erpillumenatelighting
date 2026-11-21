;;; il-model.lsp -- ilLumenate CAD toolkit: the drawing model, hints, ILCHECK rules, the ilq/2
;;; package and the import receipt. Pure: the AutoCAD commands collect the model from entities
;;; (il-commands.lsp) and CI runs everything here against the shared fixtures.
;;;
;;; Model: an association list with "drawing", "rooms", "cabinets", "runs", "styles", "psus",
;;; "wires", "controls", "zones", "others" and "overrides". A run is an association list ("id" "handle" "fixture_type"
;;; "room" "location" "style" "vertices" "closed" "breaks" "spans" "start_feed" "lead_in" "jumper_in"
;;; "feed_method" "feed_handles" "cabinet" "psu_hint" "notes" "line_key" "configured_name"
;;; "config_hash" "layout" ...). Styles are catalog style objects (IL-OBJ) with an "id". Runs and rooms
;;; carry the layout that owns them (DXF group 410; nil reads as model space).

(setq *il-package-schema* "ilq/2")
(setq *il-length-tolerance* 0.05)

(defun il-model-style (model id / found)
  (foreach style (il-get "styles" model)
    (if (and (null found) (= (il-j style "id") id)) (setq found style))
  )
  found
)

;; --- Geometry and hints -----------------------------------------------------------------------

;; ((segments . (path-result ...)) (length_in . total) (min_arc_radius_in . r))
;; ((segments . (path-result ...)) (length_in . total) (min_arc_radius_in . r)). Each segment is a lit
;; piece of the run with "jumper" (a jumper follows it) and "jumper_in" (its length when known).
(defun il-run-geometry (run / results total smallest result)
  (setq total 0.0)
  (foreach piece (il-run-pieces (il-get "vertices" run) (il-get "closed" run) (il-get "breaks" run) (il-get "spans" run) (il-get "jumper_in" run))
    (setq result (append (il-path-length (car piece) nil) (list (cons "jumper" (cadr piece)) (cons "jumper_in" (caddr piece)))))
    (setq results (cons result results) total (+ total (il-get "length_in" result)))
    (if (il-get "min_arc_radius_in" result)
      (setq smallest (if smallest (min smallest (il-get "min_arc_radius_in" result)) (il-get "min_arc_radius_in" result)))
    )
  )
  (list (cons "segments" (reverse results)) (cons "length_in" (il-round-py total 4)) (cons "min_arc_radius_in" smallest))
)

;; What the run tag and the live readout show: drawn and snapped length, watts, % of max run, splits.
(defun il-run-hint (run style catalog / geometry variant snapped cut free split watts)
  (setq geometry (il-run-geometry run) variant (if style (il-style-variant catalog style)))
  (setq snapped 0.0)
  (if variant
    (progn
      (setq cut (il-j variant "cut_mm") free (il-true-p (il-j variant "free_cut")))
      (foreach segment (il-get "segments" geometry)
        (setq snapped (+ snapped (il-get "mfg_in" (il-cut-snap (il-get "length_in" segment) cut free))))
      )
      (setq split (il-run-split snapped (il-j variant "w_per_ft") cut free (il-j variant "max_run_vd_ft") nil))
      (setq watts (if (il-j variant "w_per_ft") (il-run-watts snapped (il-j variant "w_per_ft"))))
    )
    (setq snapped (il-get "length_in" geometry))
  )
  (list
    (cons "length_in" (il-get "length_in" geometry))
    (cons "snapped_in" (il-round-py snapped 2))
    (cons "segments" (length (il-get "segments" geometry)))
    (cons "min_arc_radius_in" (il-get "min_arc_radius_in" geometry))
    (cons "watts" watts)
    (cons "max_run_ft" (il-get "max_run_ft" split))
    (cons "pct_of_max" (il-get "pct_of_max" split))
    (cons "runs_count" (if split (il-get "runs_count" split) 1))
    (cons "runs_in" (il-get "runs_in" split))
    (cons "variant" variant)
  )
)

;; "120.25 in (10'-0 1/4\") 44.1 W 54% max" for the readout and the run tag.
(defun il-hint-text (hint / text)
  (setq text (strcat (il-num->str (il-get "snapped_in" hint) 2) " in"))
  (if (il-get "watts" hint) (setq text (strcat text "  " (il-num->str (il-get "watts" hint) 1) " W")))
  (if (il-get "pct_of_max" hint) (setq text (strcat text "  " (il-num->str (il-get "pct_of_max" hint) 0) "% max")))
  (if (> (il-get "runs_count" hint) 1) (setq text (strcat text "  splits x" (itoa (il-get "runs_count" hint)))))
  text
)

;; --- ILCHECK (geometry checks; the engine and the configurators check the rest on import) -------

(defun il-issue (code ref severity text)
  (list (cons "code" code) (cons "ref" ref) (cons "severity" severity) (cons "text" text))
)

(defun il-overridden-p (issue overrides / found)
  (foreach override overrides
    (if (and (= (il-get "code" override) (il-get "code" issue)) (= (il-get "ref" override) (il-get "ref" issue)))
      (setq found T)
    )
  )
  found
)

(defun il-psu-runs (model psu-id / found)
  (foreach psu (il-get "psus" model)
    (if (= (il-get "id" psu) psu-id) (setq found (il-get "runs" psu)))
  )
  found
)

(defun il-run-fed-p (model run-id / fed)
  (foreach psu (il-get "psus" model)
    (if (member run-id (il-get "runs" psu)) (setq fed T))
  )
  (foreach wire (il-get "wires" model)
    (if (or (= (il-get "to" wire) run-id) (= (il-get "from" wire) run-id)) (setq fed T))
  )
  fed
)

;; Adds to the ISSUES list of the il-check call running (AutoLISP variables are dynamically scoped).
(defun il-add (code ref severity text)
  (setq issues (cons (il-issue code ref severity text) issues))
)

;; Every issue in the drawing: ((code ref severity text) ...). TODAY is "YYYY-MM-DD".
(defun il-check (model catalog today / issues ids id run style template profile hint variant
                                       stale ends tape-width loads driver over)
  (if (null catalog)
    (il-add "CATALOG_MISSING" "drawing" "error" "Load the CAD catalog (ILCATALOG) before checking")
  )
  (if (and catalog (setq stale (il-catalog-stale catalog today)))
    (il-add "CATALOG_STALE" "drawing" "warning" stale)
  )
  (if (and catalog (setq stale (il-toolkit-outdated catalog)))
    (il-add "TOOLKIT_OUTDATED" "drawing" "warning" stale)
  )
  (if (not (il-true-p (il-bool (il-get "scale_verified" (il-get "drawing" model)))))
    (il-add "SCALE_UNVERIFIED" "drawing" "warning" "Calibrate the underlay scale with ILSCALE")
  )
  (foreach run (il-get "runs" model)
    (setq id (il-get "id" run))
    (cond
      ((or (null id) (= id "")) (il-add "RUN_MISSING_ID" (il-get "handle" run) "error" "Run has no ID; run ILUPDATE"))
      ((member id ids) (il-add "RUN_DUPLICATE_ID" id "error" (strcat "Two runs are tagged " id "; run ILUPDATE to renumber copies")))
      (T (setq ids (cons id ids)))
    )
    (if (or (null (il-get "fixture_type" run)) (= (il-get "fixture_type" run) ""))
      (il-add "RUN_MISSING_TYPE" (if id id (il-get "handle" run)) "error" "Run has no schedule Type")
    )
    (if (null (il-get "room" run)) (il-add "RUN_NO_ROOM" id "warning" "Run is not in a room (ILROOM)"))
    (if (null (il-get "segments" (il-run-geometry run)))
      (il-add "RUN_NO_TAPE" id "error" "The whole run is marked as jumper span; take a span off with ILJUMPER")
    )
    (if (and (il-get "spans" run) (not (il-get "closed" run))
             (or (member 0 (il-get "spans" run)) (member (- (length (il-get "vertices" run)) 2) (il-get "spans" run))))
      (il-add "JUMPER_SPAN_AT_END" id "warning" "A jumper span at the run's end joins nothing and is left out; trim it, or count it in the lead (ILFEED)")
    )
    (setq style (il-model-style model (il-get "style" run)))
    (cond
      ((null style) (il-add "RUN_NO_STYLE" id "error" "Run has no style (ILSTYLE)"))
      ((and catalog (null (setq template (il-cat-template catalog (il-j style "family") (il-j style "template")))))
        (il-add "TEMPLATE_DISCONTINUED" id "error" (strcat (il-j style "template") " is not in the current catalog"))
      )
      ((and catalog (= (il-j style "family") "Extrusion Kit")
            (null (il-cat-template catalog (il-j (il-j style "tape") "family") (il-j (il-j style "tape") "template"))))
        (il-add "TEMPLATE_DISCONTINUED" id "error" (strcat (il-j (il-j style "tape") "template") " is not in the current catalog"))
      )
      (catalog
        (setq hint (il-run-hint run style catalog) variant (il-get "variant" hint))
        (if (> (abs (- (il-get "length_in" hint) (il-get "snapped_in" hint))) *il-length-tolerance*)
          (il-add "CUT_SNAP" id "info"
            (strcat "Builds " (il-num->str (il-get "snapped_in" hint) 2) " in for "
                    (il-num->str (il-get "length_in" hint) 2) " in drawn (cut increment)"))
        )
        (if (and (> (il-get "runs_count" hint) 1) (= (il-get "feed_method" run) "end"))
          (il-add "TAPE_RUN_TOO_LONG" id "warning"
            (strcat "Over the " (il-num->str (il-get "max_run_ft" hint) 1) " ft max run; the build splits into "
                    (itoa (il-get "runs_count" hint)) " runs. Choose double-end or center feed, or accept the split"))
        )
        (if (and variant (il-j variant "min_bend_radius_in") (il-get "min_arc_radius_in" hint)
                 (< (il-get "min_arc_radius_in" hint) (il-j variant "min_bend_radius_in")))
          (il-add "BEND_RADIUS" id "error"
            (strcat "Arc radius " (il-num->str (il-get "min_arc_radius_in" hint) 2) " in is under the tape's "
                    (il-num->str (il-j variant "min_bend_radius_in") 2) " in minimum"))
        )
        (setq profile (il-style-profile catalog style))
        (if (and profile (il-get "min_arc_radius_in" hint) (not (il-true-p (il-j profile "curve_capable"))))
          (il-add "PROFILE_NOT_CURVE_CAPABLE" id "error" (strcat (il-j profile "code") " cannot follow a curve"))
        )
        (setq tape-width (if variant (il-j variant "width_in")))
        (if (and profile tape-width (il-j profile "width_in") (> tape-width (il-j profile "width_in")))
          (il-add "TAPE_WIDER_THAN_PROFILE" id "error"
            (strcat "Tape is " (il-num->str tape-width 3) " in wide; " (il-j profile "code") " fits "
                    (il-num->str (il-j profile "width_in") 3) " in"))
        )
      )
    )
    (if (and id (not (il-run-fed-p model id)) (null (il-get "cabinet" run)))
      (il-add "RUN_UNCONNECTED" id "warning" "Run has no supply location (ILCONNECT or ILWIRE)")
    )
  )
  (setq ends (append ids (mapcar '(lambda (x) (il-get "id" x)) (il-get "psus" model))
                     (mapcar '(lambda (x) (il-get "id" x)) (il-get "controls" model))
                     (mapcar '(lambda (x) (il-get "id" x)) (il-get "cabinets" model))))
  (foreach wire (il-get "wires" model)
    (foreach end (list (il-get "from" wire) (il-get "to" wire))
      (if (not (member end ends)) (il-add "WIRE_UNKNOWN_END" (il-get "id" wire) "error" (strcat "Wire end " (il-str end) " is not a run, PSU or cabinet")))
    )
  )
  ;; Provisional PSU load (the designer sizes and assigns; this is only the tag's hint).
  (foreach psu (il-get "psus" model)
    (setq driver nil)
    (if (and catalog (il-get "item_code" psu))
      (foreach item (il-items (il-j catalog "drivers"))
        (if (= (il-j item "code") (il-get "item_code" psu)) (setq driver item))
      )
    )
    (if (and driver (il-j driver "rated_w"))
      (progn
        (setq loads nil)
        (foreach run (il-get "runs" model)
          (if (member (il-get "id" run) (il-get "runs" psu))
            (progn
              (setq hint (il-run-hint run (il-model-style model (il-get "style" run)) catalog))
              (if (il-get "watts" hint) (setq loads (cons (il-get "watts" hint) loads)))
            )
          )
        )
        (setq over (il-psu-load loads (il-j driver "rated_w") (il-j driver "usable_load_factor")))
        (if (il-get "over" over)
          (il-add "PSU_OVERLOAD" (il-get "id" psu) "warning"
            (strcat (il-num->str (il-get "total_w" over) 1) " W on " (il-num->str (il-get "usable_w" over) 1)
                    " W usable; the System Designer will reassign outputs"))
        )
      )
    )
  )
  (append (reverse issues) (il-check-controls model catalog))
)

;; (errors warnings): issues an override covers do not count.
(defun il-issue-counts (issues overrides / errors warnings)
  (setq errors 0 warnings 0)
  (foreach issue issues
    (if (not (il-overridden-p issue overrides))
      (cond
        ((= (il-get "severity" issue) "error") (setq errors (1+ errors)))
        ((= (il-get "severity" issue) "warning") (setq warnings (1+ warnings)))
      )
    )
  )
  (list errors warnings)
)

;; --- Sheets -------------------------------------------------------------------------------------

;; A CadId for a layout name (^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$): other characters become one "-",
;; leading and trailing punctuation goes, at most 40 characters. Model space (nil) is "Model".
(defun il-sheet-slug (layout / text index char code out)
  (setq text (if (and layout (/= (il-trim layout) "")) (il-trim layout) "Model") index 1 out "")
  (while (<= index (strlen text))
    (setq char (substr text index 1) code (ascii char) index (1+ index))
    (cond
      ((or (< 47 code 58) (< 64 code 91) (< 96 code 123) (member char '("." "_" "-"))) (setq out (strcat out char)))
      ((and (/= out "") (/= (substr out (strlen out) 1) "-")) (setq out (strcat out "-")))
    )
  )
  (while (and (/= out "") (member (substr out 1 1) '("." "_" "-"))) (setq out (substr out 2)))
  (setq out (vl-string-right-trim "._-" (substr out 1 40)))
  (if (= out "") "Sheet" out)
)

;; SLUG made unique among USED ids: "Level-1", then "Level-1-2", "Level-1-3" (kept within 40 characters).
(defun il-unique-slug (slug used / number suffix candidate)
  (setq candidate slug number 1)
  (while (member candidate used)
    (setq number (1+ number) suffix (strcat "-" (itoa number))
          candidate (strcat (vl-string-right-trim "._-" (substr slug 1 (- 40 (strlen suffix)))) suffix))
  )
  candidate
)

;; The layout a run or room is on: its "layout", model space when it has none.
(defun il-item-layout (item / layout)
  (setq layout (il-get "layout" item))
  (if (and layout (/= (il-trim layout) "")) layout "Model")
)

;; The model's sheets: one per layout that owns a run, in the order the runs first use them, as
;; ((("layout" . name) ("id" . cad-id) ("label" . name)) ...).
(defun il-model-sheets (model / sheets layout ids id)
  (foreach run (il-get "runs" model)
    (setq layout (il-item-layout run))
    (if (null (il-sheet-for sheets layout))
      (setq id (il-unique-slug (il-sheet-slug layout) ids) ids (cons id ids)
            sheets (append sheets (list (list (cons "layout" layout) (cons "id" id) (cons "label" (substr layout 1 120))))))
    )
  )
  sheets
)

;; The sheet id of LAYOUT among SHEETS (nil when no run is on it).
(defun il-sheet-for (sheets layout / found)
  (foreach sheet sheets
    (if (and (null found) (= (il-get "layout" sheet) layout)) (setq found (il-get "id" sheet)))
  )
  found
)

;; How far the sheets' scale can be trusted: ILSCALE calibrated it ("verified"), or only the drawing's
;; units say it ("declared"; an AutoCAD drawing always has units).
(defun il-scale-status (drawing)
  (if (il-true-p (il-bool (il-get "scale_verified" drawing))) "verified" "declared")
)

(defun il-package-sheets (sheets drawing / status)
  (setq status (il-scale-status drawing))
  (il-arr (mapcar '(lambda (sheet)
                     (il-obj (list (cons "id" (il-get "id" sheet)) (cons "label" (il-get "label" sheet))
                                   (cons "scale" (il-obj (list (cons "status" status) (cons "unit" "in")))))))
                  sheets))
)

;; --- ilq/2 package ----------------------------------------------------------------------------

(defun il-opt (key value pairs)
  (if (and value (/= value "")) (append pairs (list (cons key value))) pairs)
)

(defun il-package-style (style / pairs tape)
  (setq pairs nil)
  (if (il-starts-with (il-str (il-j style "id")) "preset:")
    (setq pairs (list (cons "preset" (il-style-label style))))
  )
  (setq pairs (append pairs (list (cons "family" (il-j style "family")) (cons "template" (il-j style "template"))
                                  (cons "selections" (if (il-j style "selections") (il-j style "selections") (il-obj nil))))))
  (if (il-j style "segments") (setq pairs (append pairs (list (cons "segments" (il-j style "segments"))))))
  (if (setq tape (il-j style "tape"))
    (setq pairs (append pairs (list (cons "tape" (il-obj (list (cons "family" (il-j tape "family"))
                                                               (cons "template" (il-j tape "template"))
                                                               (cons "selections" (if (il-j tape "selections") (il-j tape "selections") (il-obj nil))))))))))
  (il-obj pairs)
)

(defun il-package-segments (run / geometry results index count pairs)
  (setq geometry (il-run-geometry run) results (il-get "segments" geometry) index 0 count (length results))
  (mapcar
    '(lambda (segment / pairs)
       (setq pairs (list (cons "path_length_in" (il-get "length_in" segment))))
       (if (= index 0)
         (setq pairs (il-opt "start_feed" (il-get "start_feed" run) pairs)
               pairs (if (il-get "lead_in" run) (append pairs (list (cons "lead_length_in" (il-get "lead_in" run)))) pairs))
       )
       (setq pairs (append pairs (list (cons "end_type" (if (and (< index (1- count)) (il-get "jumper" segment)) "JUMPER" "ENDCAP")))))
       (if (and (< index (1- count)) (il-get "jumper" segment) (il-get "jumper_in" segment))
         (setq pairs (append pairs (list (cons "jumper_length_in" (il-get "jumper_in" segment)))))
       )
       (if (il-get "min_arc_radius_in" segment)
         (setq pairs (append pairs (list (cons "min_arc_radius_in" (il-get "min_arc_radius_in" segment)))))
       )
       (setq index (1+ index))
       (il-obj pairs)
     )
    results
  )
)

;; SHEETS: il-model-sheets of MODEL.
(defun il-package-run (model run sheets / pairs erp)
  (setq pairs (list (cons "id" (il-get "id" run)) (cons "handle" (il-get "handle" run)) (cons "identity" "xdata")))
  (setq pairs (il-opt "sheet" (il-sheet-for sheets (il-item-layout run)) pairs))
  (setq pairs (il-opt "room" (il-get "room" run) pairs))
  (setq pairs (append pairs (list (cons "fixture_type" (il-get "fixture_type" run)))))
  (setq pairs (il-opt "location" (il-get "location" run) pairs))
  (setq pairs (append pairs
    (list
      (cons "style" (il-package-style (il-model-style model (il-get "style" run))))
      (cons "segments" (il-arr (il-package-segments run)))
      (cons "feed" (il-obj (list (cons "method" (if (il-get "feed_method" run) (il-get "feed_method" run) "end"))
                                 (cons "point_handles" (il-arr (il-get "feed_handles" run))))))
    )))
  (setq pairs (il-opt "cabinet" (il-get "cabinet" run) pairs))
  (setq pairs (il-opt "psu_hint" (il-get "psu_hint" run) pairs))
  (setq pairs (il-opt "notes" (il-get "notes" run) pairs))
  (setq erp (il-opt "line_key" (il-get "line_key" run) nil))
  (setq erp (il-opt "configured_name" (il-get "configured_name" run) erp))
  (setq erp (il-opt "config_hash" (il-get "config_hash" run) erp))
  (il-obj (append pairs (list (cons "erp" (il-obj erp)))))
)

;; The ilq/2 package for MODEL. ISSUES are il-check's result; PLATFORM names the AutoCAD product.
;; Each layout with runs is a sheet; runs and rooms name theirs (a room only when its layout has runs).
(defun il-package (model catalog issues platform / drawing counts overrides sheets)
  (setq drawing (il-get "drawing" model) overrides (il-get "overrides" model) sheets (il-model-sheets model))
  (setq counts (il-issue-counts issues overrides))
  (il-obj
    (list
      (cons "schema" *il-package-schema*)
      (cons "toolkit" (il-obj (list (cons "version" *il-version*) (cons "platform" platform))))
      (cons "source" (il-obj (list (cons "tool" "autocad") (cons "version" *il-version*) (cons "platform" platform)
                                   (cons "input" "ilq"))))
      (cons "sheets" (il-package-sheets sheets drawing))
      (cons "catalog" (il-obj (list (cons "snapshot_hash" (il-j catalog "snapshot_hash"))
                                    (cons "hash" (il-j catalog "hash"))
                                    (cons "generated_at" (il-str (il-j catalog "generated_at"))))))
      (cons "target" (il-obj (list (cons "schedule" (il-str (il-get "schedule" drawing)))
                                   (cons "schedule_version" (if (il-get "schedule_version" drawing) (il-get "schedule_version" drawing) 0))
                                   (cons "project" (il-str (il-get "project" drawing))))))
      (cons "drawing" (il-obj (list (cons "file" (il-get "file" drawing))
                                    (cons "rev" (if (il-get "rev" drawing) (il-get "rev" drawing) 0))
                                    (cons "hash" (il-get "hash" drawing))
                                    (cons "units" "in")
                                    (cons "scale_verified" (il-bool (il-get "scale_verified" drawing))))))
      (cons "rooms" (il-arr (mapcar '(lambda (room)
                                       (il-obj (il-opt "sheet" (il-sheet-for sheets (il-item-layout room))
                                                 (list (cons "id" (il-get "id" room)) (cons "name" (il-get "name" room))
                                                       (cons "level" (il-str (il-get "level" room)))
                                                       (cons "env" (if (il-get "env" room) (il-get "env" room) "dry-concealed"))))))
                                    (il-get "rooms" model))))
      (cons "cabinets" (il-arr (mapcar '(lambda (cabinet)
                                          (il-obj (il-opt "room" (il-get "room" cabinet)
                                                    (list (cons "id" (il-get "id" cabinet))
                                                          (cons "location_rating" (if (il-get "location_rating" cabinet) (il-get "location_rating" cabinet) "Dry"))
                                                          (cons "access_note" (il-str (il-get "access_note" cabinet)))))))
                                       (il-get "cabinets" model))))
      (cons "runs" (il-arr (mapcar '(lambda (run) (il-package-run model run sheets)) (il-get "runs" model))))
      (cons "psus" (il-arr (mapcar '(lambda (psu)
                                      (il-obj (il-opt "item_code" (il-get "item_code" psu)
                                                (il-opt "cabinet" (il-get "cabinet" psu)
                                                  (list (cons "id" (il-get "id" psu))
                                                        (cons "runs" (il-arr (il-get "runs" psu))))))))
                                   (il-get "psus" model))))
      (cons "wire_paths" (il-arr (mapcar '(lambda (wire)
                                            (il-obj (list (cons "id" (il-get "id" wire)) (cons "from" (il-get "from" wire))
                                                          (cons "to" (il-get "to" wire)) (cons "kind" (il-get "kind" wire))
                                                          (cons "path_length_in" (il-get "length_in" wire)))))
                                         (il-get "wires" model))))
      (cons "check" (il-obj (list (cons "errors" (car counts)) (cons "warnings" (cadr counts))
                                  (cons "overrides" (il-arr (mapcar '(lambda (o)
                                                                       (il-obj (list (cons "code" (il-get "code" o)) (cons "ref" (il-get "ref" o))
                                                                                     (cons "note" (il-get "note" o)))))
                                                                    overrides))))))
      (cons "controls" (il-package-controls model))
      (cons "zones" (il-package-zones model))
      (cons "other_lines" (il-arr (il-get "others" model)))
    )
  )
)

;; What the drawing's content hash covers: the package without who wrote it, when, the drawing's
;; file, scale and check state, the catalog, or the sheets (layout names and scale status are not what
;; was drawn, and leaving them out keeps hashes from 0.4.x toolkits stable).
(defun il-package-content (package / strip)
  (setq strip '(("runs" "sheet" "identity") ("rooms" "sheet")))
  (il-obj
    (mapcar
      '(lambda (pair)
         (if (assoc (car pair) strip)
           (cons (car pair)
                 (il-arr (mapcar '(lambda (item)
                                    (il-obj (vl-remove-if '(lambda (field) (member (car field) (cdr (assoc (car pair) strip)))) (cdr item))))
                                 (il-items (cdr pair)))))
           pair
         )
       )
      (vl-remove-if '(lambda (pair) (member (car pair) '("toolkit" "source" "drawing" "check" "catalog" "sheets"))) (cdr package))
    )
  )
)

;; The drawing's content hash: what was drawn, not when or by whom.
(defun il-model-hash (model catalog)
  (il-sha256 (il-json-text (il-package-content (il-package model catalog nil "hash"))))
)

;; --- Receipt (ilq-receipt/1) ------------------------------------------------------------------

;; ((run-id . receipt-run-object) ...) from a receipt the portal wrote.
(defun il-receipt-index (receipt)
  (if (= (il-j receipt "schema") "ilq-receipt/1")
    (mapcar '(lambda (run) (cons (il-j run "id") run)) (il-items (il-j receipt "runs")))
  )
)

;; ((control-id . line-key) ...) from a receipt (controls in v1).
(defun il-receipt-controls (receipt)
  (if (= (il-j receipt "schema") "ilq-receipt/1")
    (mapcar '(lambda (pair) (cons (car pair) (cdr pair))) (cdr (il-j receipt "controls")))
  )
)

;; The run with the receipt's ERP keys, part number and server length stamped on it.
(defun il-run-with-receipt (run index / entry)
  (if (setq entry (cdr (assoc (il-get "id" run) index)))
    (progn
      (foreach key '("line_key" "configured_name" "config_hash" "part_number")
        (setq run (il-put key (il-j entry key) run))
      )
      (il-put "server_in" (il-j entry "server_length_in") run)
    )
    run
  )
)
