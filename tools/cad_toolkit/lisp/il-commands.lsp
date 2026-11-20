;;; il-commands.lsp -- ilLumenate CAD toolkit commands (draw-to-quote plan 3.3-3.9, 4.1-4.5).
;;;
;;; AutoCAD draws the geometry; the portal builds the products. Runs are LWPOLYLINEs with XData; rooms
;;; are closed polylines; cabinets, PSUs and tags are blocks. Hints (snap, % of max run, PSU load) come
;;; from il-math and are only hints: the import's server numbers win. No PSU sizing, voltage drop,
;;; stick packing or BOM math happens here. Command line only, so LT 2024+ and Mac work too.

(setq *il-style* nil *il-fixture-type* "L1")

(setq *il-env-choices*
  '("dry-concealed" "in-wall" "plenum" "riser" "raceway" "damp" "wet" "outdoor-exposed" "direct-burial"))

;; --- Catalog and styles -----------------------------------------------------------------------

(defun il-catalog (/ path)
  (if (null *il-catalog*)
    (progn
      (setq path (cond ((il-setting "catalog_path")) ((getenv "ILLUMENATE_CATALOG"))))
      (if (and path (findfile path)) (setq *il-catalog* (il-catalog-read path) *il-catalog-path* path))
    )
  )
  *il-catalog*
)

(defun il-require-catalog ()
  (if (null (il-catalog))
    (progn (princ "\nLoad the CAD catalog first: ILCATALOG.") (exit))
  )
  *il-catalog*
)

(defun il-styles () (il-items (il-fetch-json "STYLES")))

(defun il-save-style (style / styles kept)
  (foreach item (il-styles)
    (if (/= (il-j item "id") (il-j style "id")) (setq kept (cons item kept)))
  )
  (setq styles (cons style (reverse kept)))
  (il-store-json "STYLES" (il-arr styles))
  style
)

(defun il-style-by-id (id / found)
  (foreach style (il-styles) (if (= (il-j style "id") id) (setq found style)))
  found
)

;; --- ILCATALOG, ILSETUP --------------------------------------------------------------------------

(defun c:ILCATALOG (/ path catalog stale)
  (il-begin)
  (setq path (getfiled "ilLumenate CAD catalog" (if *il-catalog-path* *il-catalog-path* "") "json" 0))
  (cond
    ((null path))
    ((null (setq catalog (il-catalog-read path)))
      (princ (strcat "\nCould not read the catalog: " (il-str *il-jr-error*))))
    (T
      (setq *il-catalog* catalog *il-catalog-path* path)
      (setenv "ILLUMENATE_CATALOG" path)
      (il-set-setting "catalog_path" path)
      (il-set-setting "snapshot_hash" (il-j catalog "snapshot_hash"))
      (il-set-setting "catalog_hash" (il-j catalog "hash"))
      (princ (strcat "\nCatalog " (substr (il-str (il-j catalog "hash")) 1 8) " loaded: "
                     (itoa (length (il-items (il-j catalog "templates")))) " tape and neon templates, "
                     (itoa (length (il-items (il-j catalog "styles")))) " run styles."))
      (if (setq stale (il-catalog-stale catalog (il-today))) (princ (strcat "\n" stale)))
    )
  )
  (il-end)
)

(defun c:ILSETUP (/ schedule project size scale old-scale tb point)
  (il-begin)
  (il-assets-ensure)
  (if (/= (getvar "INSUNITS") 1)
    (princ "\nThis drawing is not in inches (INSUNITS=1). Lengths are read as inches; check the units.")
  )
  (setq schedule (il-ask "Portal schedule name (blank for none yet)" (il-str (il-setting "schedule"))))
  (setq project (il-ask "Portal project" (il-str (il-setting "project"))))
  (il-set-setting "schedule" schedule)
  (il-set-setting "project" project)
  (setq old-scale (il-symbol-scale))
  (initget 6)
  (setq scale (getreal (strcat "\nPlot scale factor for symbols (48 for 1/4\"=1'-0\") <" (il-num->str old-scale 2) ">: ")))
  (if scale
    (progn
      (il-set-setting "symbol_scale" scale)
      (if (not (equal scale old-scale 1e-9))
        (princ (strcat "\nResized " (itoa (il-rescale-symbols (/ (float scale) old-scale))) " placed symbols to the new scale."
                       " Place DMX and output tables again (ILDMX, ILOUT) if you have them."))
      )
    )
    (il-set-setting "symbol_scale" old-scale)
  )
  (if (setq size (il-choose "Title block" '("None" "ARCH-D" "ARCH-C" "ANSI-D" "ANSI-B" "ANSI-A") 1))
    (if (/= size "None")
      (progn
        (setq point (getpoint "\nTitle block lower-left corner <0,0>: "))
        (setq tb (il-insert (strcat "IL-TB-" size) (if point point '(0.0 0.0 0.0))
                            (if (il-paper-space-p) 1.0 (il-symbol-scale)) "E-ANNO-TTLB"
                   (list (cons "PROJECT" project) (cons "NUMBER" schedule) (cons "DATE" (il-today))
                         (cons "SCALE" (il-scale-text (il-symbol-scale)))
                         (cons "SHEET_TITLE" "LIGHTING PLAN") (cons "STAMP" "FOR REFERENCE"))))
        (princ (if (il-paper-space-p)
                 "\nTitle block placed full size on this layout."
                 (strcat "\nTitle block placed in model space at the plot scale (" (il-scale-text (il-symbol-scale))
                         "). On a layout tab it goes in full size.")))
      )
    )
  )
  (if (not (il-catalog)) (princ "\nNext: ILCATALOG to load the CAD catalog downloaded from the portal."))
  (princ "\nLayers and blocks are ready.")
  (il-end)
)

;; --- ILSTYLE ----------------------------------------------------------------------------------

(defun il-new-tape-style (catalog family / templates names template selections option value label choice values at)
  (foreach item (il-items (il-j catalog "templates"))
    (if (= (il-j item "family") family) (setq templates (cons item templates)))
  )
  (setq templates (reverse templates) names (mapcar '(lambda (item) (strcat (il-str (il-j item "code")) "  " (il-str (il-j item "name")))) templates))
  (if (null templates) (progn (princ (strcat "\nThe catalog has no " family " templates.")) (exit)))
  (if (null (setq choice (il-choose (strcat family " template") names 1))) (exit))
  (setq template (nth (vl-position choice names) templates))
  (foreach option (il-items (il-j template "options"))
    (setq values (il-items (il-j option "values")) at (vl-position (il-j option "default") values))
    (setq value (il-choose (il-str (il-j option "label")) values (if at (1+ at) 1)))
    (if value (setq selections (append selections (list (cons (il-j option "key") value)))))
  )
  (setq label (il-trim (il-ask "Style name" (strcat (il-j template "code") " " (il-join (mapcar 'cdr selections) " ")))))
  (il-obj (list (cons "id" (strcat "custom:" label)) (cons "label" label) (cons "family" family)
                (cons "template" (il-j template "code")) (cons "selections" (il-obj selections))))
)

(defun il-pick-style (styles title / names choice)
  (setq names (mapcar '(lambda (style) (strcat (il-style-label style) "  [" (il-j style "family") "]")) styles))
  (if (setq choice (il-choose title names 1)) (nth (vl-position choice names) styles))
)

(defun c:ILSTYLE (/ catalog source family style tape presets kits)
  (il-begin)
  (setq catalog (il-require-catalog))
  (setq source (il-choose "Run style"
                 (append (if (il-styles) '("Recent style in this drawing")) '("Saved preset" "New tape or neon style"))
                 1))
  (cond
    ((= source "Recent style in this drawing") (setq style (il-pick-style (il-styles) "Styles in this drawing")))
    ((= source "Saved preset")
      (setq presets (il-items (il-j catalog "styles")))
      (if (null presets)
        (princ "\nNo presets in the catalog. Save presets in the portal configurator, then download the catalog again.")
        (setq style (il-pick-style presets "Presets"))
      )
    )
    ((= source "New tape or neon style")
      (setq family (il-choose "Family" '("LED Tape" "COB Tape" "LED Neon") 1))
      (if family (setq style (il-new-tape-style catalog family)))
    )
  )
  (if (and style (= (il-j style "family") "Extrusion Kit") (null (il-j style "tape")))
    (progn
      (princ "\nA kit run needs the tape that goes in it.")
      (setq kits (vl-remove-if-not '(lambda (item) (il-tape-family-p (il-j item "family")))
                                   (append (il-styles) (il-items (il-j catalog "styles")))))
      (setq tape (if kits (il-pick-style kits "Tape for the kit") (il-new-tape-style catalog "LED Tape")))
      (if tape
        (progn
          (setq style (il-jset style "tape" (il-obj (list (cons "family" (il-j tape "family")) (cons "template" (il-j tape "template"))
                                                          (cons "selections" (il-j tape "selections"))))))
          (setq style (il-jset style "id" (strcat (il-j style "id") "+" (il-str (il-j tape "template")))))
        )
        (progn (princ "\nNo tape chosen; the kit style was not kept.") (setq style nil))
      )
    )
  )
  (if style
    (progn
      (il-save-style style)
      (setq *il-style* (il-j style "id"))
      (il-set-setting "current_style" *il-style*)
      (princ (strcat "\nCurrent style: " (il-style-label style)))
    )
  )
  (il-end)
)

;; --- Runs: ILTAPE, ILCONVERT, ILJUMPER -------------------------------------------------------------

(defun il-run-layer (style)
  (if (member (il-j style "family") '("Linear Fixture" "Extrusion Kit")) "E-LITE-EXTR" "E-LITE-TAPE")
)

;; The run as the model sees it, from its polyline and XData.
(defun il-run-from-entity (ename / x)
  (setq x (il-xget ename))
  (list
    (cons "ename" ename)
    (cons "id" (il-get "id" x))
    (cons "handle" (il-handle ename))
    (cons "fixture_type" (il-get "type" x))
    (cons "room" (il-get "room" x))
    (cons "location" (il-get "location" x))
    (cons "style" (il-get "style" x))
    (cons "vertices" (il-lw-vertices ename))
    (cons "closed" (il-lw-closed ename))
    (cons "breaks" (il-run-breaks x))
    (cons "spans" (il-run-spans x))
    (cons "start_feed" (il-get "start_feed" x))
    (cons "lead_in" (il-number (il-get "lead_in" x)))
    (cons "jumper_in" (il-number (il-get "jumper_in" x)))
    (cons "feed_method" (if (il-get "feed" x) (il-get "feed" x) "end"))
    (cons "feed_handles" (if (il-get "feed_handles" x) (il-split (il-get "feed_handles" x) ",")))
    (cons "cabinet" (il-get "cabinet" x))
    (cons "psu_hint" (il-get "psu_hint" x))
    (cons "notes" (il-get "notes" x))
    (cons "line_key" (il-get "line_key" x))
    (cons "configured_name" (il-get "configured_name" x))
    (cons "config_hash" (il-get "config_hash" x))
    (cons "part_number" (il-get "part_number" x))
    (cons "server_in" (il-number (il-get "server_in" x)))
  )
)

;; Colour by state: green ok, yellow a hint to look at, red an error (ByLayer once imported).
(defun il-color-run (ename severity / data color)
  (setq color (cond ((= severity "error") 1) ((= severity "warning") 2) ((= severity "imported") 256) (T 3)))
  (setq data (entget ename))
  (entmod (if (assoc 62 data) (subst (cons 62 color) (assoc 62 data) data) (append data (list (cons 62 color)))))
)

;; Ask what to do when the run is over the max run (a proposal; the configurator builds it).
(defun il-over-max (ename hint / answer)
  (princ (strcat "\nOver the " (il-num->str (il-get "max_run_ft" hint) 1) " ft max run ("
                 (il-num->str (il-get "pct_of_max" hint) 0) "%). The build splits into "
                 (itoa (il-get "runs_count" hint)) " runs: " (il-join (mapcar '(lambda (x) (il-num->str x 2)) (il-get "runs_in" hint)) " + ") " in."))
  (initget "Split Double Center")
  (setq answer (getkword "\nFeed [Split into runs/Double-end/Center] <Split>: "))
  (cond
    ((= answer "Double") (il-xupdate ename '(("feed" . "double-end"))))
    ((= answer "Center") (il-xupdate ename '(("feed" . "center"))))
    (T (il-xupdate ename '(("feed" . "end")))
       (il-add-override "TAPE_RUN_TOO_LONG" (il-get "id" (il-xget ename)) "Split into runs at the configurator's max run"))
  )
)

;; Turn ENAME (an LWPOLYLINE) into a run of the current style; returns the run id.
(defun il-make-run (ename fixture-type / style id layer data hint)
  (setq style (il-style-by-id *il-style*) id (il-next-id "RUN" (strcat fixture-type "-")))
  (setq layer (il-run-layer style) data (entget ename))
  (entmod (subst (cons 8 layer) (assoc 8 data) data))
  (il-xset ename (list (cons "kind" "RUN") (cons "id" id) (cons "type" fixture-type) (cons "style" *il-style*)
                       (cons "start_feed" "End") (cons "lead_in" "0") (cons "feed" "end")))
  (setq hint (il-run-hint (il-run-from-entity ename) style (il-catalog)))
  (princ (strcat "\n" id ": " (il-hint-text hint)))
  (if (> (il-get "runs_count" hint) 1) (il-over-max ename hint))
  (il-color-run ename (if (> (il-get "runs_count" hint) 1) "warning" "ok"))
  (il-tag-run ename)
  id
)

(defun il-require-style ()
  (if (null *il-style*) (setq *il-style* (il-setting "current_style")))
  (if (not (il-style-by-id *il-style*))
    (progn (princ "\nChoose a run style first: ILSTYLE.") (exit))
  )
)

(defun il-ask-type ()
  (if (and (= *il-fixture-type* "L1") (il-setting "fixture_type")) (setq *il-fixture-type* (il-setting "fixture_type")))
  (setq *il-fixture-type* (il-trim (il-ask "Schedule Type for these runs (for example L1)" *il-fixture-type*)))
  (if (= *il-fixture-type* "") (setq *il-fixture-type* "L1"))
  (il-set-setting "fixture_type" *il-fixture-type*)
)

(defun c:ILTAPE (/ before ename more count)
  (il-begin)
  (il-require-catalog)
  (il-require-style)
  (il-ask-type)
  (setvar "CLAYER" (progn (il-assets-ensure) (il-run-layer (il-style-by-id *il-style*))))
  (setq more T count 0)
  (while more
    (princ (if (= count 0)
             "\nDraw the run from its feed end (lines and arcs). Enter finishes the run."
             "\nDraw the next run of this style, or press Enter to stop."))
    (setq before (entlast))
    (command "_.PLINE")
    (while (> (getvar "CMDACTIVE") 0) (command pause))
    (setq ename (entlast))
    (cond
      ((or (null ename) (equal before ename) (/= (cdr (assoc 0 (entget ename))) "LWPOLYLINE")) (setq more nil))
      ((< (il-get "length_in" (il-path-length (il-lw-vertices ename) (il-lw-closed ename))) 0.01)
        (entdel ename)
        (princ "\nThat run has no length and was not kept."))
      (T (il-make-run ename *il-fixture-type*) (setq count (1+ count)))
    )
  )
  (if (> count 1) (princ (strcat "\n" (itoa count) " runs drawn.")))
  (il-end)
)

(defun c:ILCONVERT (/ ss index ename pieces closed join chains made count skipped tolerance vertices closed-p)
  (il-begin)
  (il-require-catalog)
  (il-require-style)
  (princ "\nSelect lines, arcs and polylines to make into runs of the current style.")
  (if (setq ss (ssget '((0 . "LWPOLYLINE,LINE,ARC"))))
    (progn
      (setq index 0 count 0 skipped 0)
      (repeat (sslength ss)
        (setq ename (ssname ss index) index (1+ index))
        (cond
          ((il-kind ename) (setq skipped (1+ skipped)))
          ((and (= (cdr (assoc 0 (entget ename))) "LWPOLYLINE") (il-lw-closed ename)) (setq closed (cons ename closed)))
          (T (setq pieces (cons ename pieces)))
        )
      )
      (setq pieces (reverse pieces) closed (reverse closed))
      (if (> (length pieces) 1)
        (progn
          (initget "Yes No")
          (setq join (/= (getkword "\nJoin pieces that meet end to end into one run? [Yes/No] <Yes>: ") "No"))
        )
      )
      (if (or pieces closed) (il-ask-type))
      (setq tolerance (max 0.01 (* 0.005 (il-symbol-scale))))
      (setq index 0)
      (setq chains (if join
                     (il-chain-pieces (mapcar 'il-piece-of pieces) tolerance)
                     (mapcar '(lambda (e) (setq index (1+ index)) (cons (il-piece-of e) (list (1- index)))) pieces)))
      (setvar "CLAYER" (progn (il-assets-ensure) (il-run-layer (il-style-by-id *il-style*))))
      (foreach chain chains
        (setq vertices (car chain))
        (if (and (null (cddr chain)) (= (cdr (assoc 0 (entget (nth (cadr chain) pieces)))) "LWPOLYLINE"))
          (setq made (nth (cadr chain) pieces))
          (progn
            (setq closed-p (and (> (length vertices) 2) (il-same-point (car vertices) (last vertices) tolerance)))
            (if closed-p (setq vertices (il-butlast vertices)))
            (setq made (il-make-lwpolyline vertices closed-p (nth (cadr chain) pieces)))
            (foreach i (cdr chain) (entdel (nth i pieces)))
          )
        )
        (il-make-run made *il-fixture-type*)
        (setq count (1+ count))
      )
      (foreach ename closed (il-make-run ename *il-fixture-type*) (setq count (1+ count)))
      (princ (strcat "\n" (itoa count) " runs made"
                     (if (> skipped 0) (strcat "; " (itoa skipped) " were already ilLumenate objects and were left as they are") "")
                     "."))
    )
  )
  (il-end)
)

;; The index of the vertex of ENAME nearest POINT.
(defun il-nearest-vertex (ename point / best best-distance index d)
  (setq index 0)
  (foreach vertex (il-lw-vertices ename)
    (setq d (distance (list (car vertex) (cadr vertex)) (list (car point) (cadr point))))
    (if (or (null best-distance) (< d best-distance)) (setq best index best-distance d))
    (setq index (1+ index))
  )
  best
)

(defun il-run-breaks (x) (if (il-get "breaks" x) (mapcar 'atoi (il-split (il-get "breaks" x) ","))))

;; ILJUMPER: pick the run where a jumper joins two segments. At a vertex the jumper goes there (pick it
;; again to take it off); elsewhere on a line or arc a vertex is added at that point.
(defun c:ILJUMPER (/ picked ename vertices target index x breaks spans cable removed group)
  (il-begin)
  (initget "Span")
  (setq picked (entsel "\nPick the run where a jumper joins it, or [Span] to mark a gap the jumper crosses: "))
  (if (= picked "Span")
    (setq picked (entsel "\nPick the run where the tape stops (start of the gap, or an existing span to remove it): ")
          group T)
  )
  (cond
    ((not (and (listp picked) picked (= (il-kind (setq ename (car picked))) "RUN")))
      (princ "\nThat is not an ilLumenate run."))
    (group (il-jumper-span ename (cadr picked)))
    (T
      (setq vertices (il-lw-vertices ename) x (il-xget ename) breaks (il-run-breaks x) spans (il-run-spans x))
      (setq target (il-jumper-target vertices (cadr picked) (* 0.1 (il-symbol-scale))))
      (cond
        ((and (= (car target) "split") (member (cadr target) spans))
          (il-jumper-span ename (cadr picked)) (setq index 'done))
        ((= (car target) "split")
          (setq index (il-run-vertex-at ename (cadr picked)) x (il-xget ename) breaks (vl-sort (cons index (il-run-breaks x)) '<)))
        ((or (= (cadr target) 0) (= (cadr target) (1- (length vertices))))
          (setq index nil))
        ((member (cadr target) breaks)
          (setq breaks (vl-remove (cadr target) breaks) index (cadr target) removed T))
        (T (setq index (cadr target) breaks (vl-sort (cons index breaks) '<)))
      )
      (cond
        ((eq index 'done))
        ((null index) (princ "\nThat is the end of the run. A jumper joins two segments: pick a point along the run."))
        (T
          (if (not removed)
            (progn
              (initget 4)
              (setq cable (getreal (strcat "\nJumper cable length in inches <" (if (il-get "jumper_in" x) (il-get "jumper_in" x) "12") ">: ")))
            )
          )
          (il-xupdate ename (list (cons "breaks" (il-join breaks ","))
                                  (cons "jumper_in" (if cable (il-num->str cable 2) (if (il-get "jumper_in" x) (il-get "jumper_in" x) "12")))))
          (princ (strcat "\n" (il-get "id" x) ": " (if removed "jumper removed; " "")
                         (if breaks (strcat (itoa (1+ (length breaks))) " segments joined by " (itoa (length breaks))
                                            " jumper" (if (= (length breaks) 1) "" "s") " of " (il-str (il-get "jumper_in" (il-xget ename))) " in.")
                                    "no jumpers at points.")))
          (il-tag-run ename)
        )
      )
    )
  )
  (il-end)
)

(setq *il-feed-directions* '("End" "Back" "Left" "Right" "Side" "Endcap"))

;; ILFEED: pick the run near the end where power comes in. The run is turned round if it was drawn
;; from the other end (the feed is always its first vertex), then the feed details are asked.
(defun c:ILFEED (/ picked ename x vertices lead feed method)
  (il-begin)
  (if (and (setq picked (entsel "\nPick the run near the end where power feeds in: "))
           (= (il-kind (setq ename (car picked))) "RUN"))
    (progn
      (setq vertices (il-lw-vertices ename) x (il-xget ename))
      (if (and (not (il-lw-closed ename))
               (< (distance (il-xy (last vertices)) (il-xy (cadr picked))) (distance (il-xy (car vertices)) (il-xy (cadr picked)))))
        (progn
          (il-lw-set-vertices ename (il-reverse-vertices vertices))
          (il-save-run-links ename (il-reverse-breaks (il-run-breaks x) (length vertices)) (il-reverse-spans (il-run-spans x) (length vertices)))
          (princ "\nRun turned round: it now starts at this end.")
        )
      )
      (setq x (il-xget ename))
      (setq feed (il-choose "Start feed direction (where the lead leaves the tape)" *il-feed-directions*
                            (1+ (if (vl-position (il-get "start_feed" x) *il-feed-directions*) (vl-position (il-get "start_feed" x) *il-feed-directions*) 0))))
      (initget 4)
      (setq lead (getreal (strcat "\nLead cable from the run to its power supply, inches <" (il-str (il-get "lead_in" x)) ">: ")))
      (initget "End Double Center Multi")
      (setq method (getkword (strcat "\nFeed method [End/Double-end/Center/Multi-feed] <" (il-str (il-get "feed" x)) ">: ")))
      (il-xupdate ename (list (cons "start_feed" (if feed feed (il-get "start_feed" x)))
                              (cons "lead_in" (if lead (il-num->str lead 2) (il-get "lead_in" x)))
                              (cons "feed" (cond ((= method "Double") "double-end") ((= method "Center") "center") ((= method "Multi") "multi-feed") ((= method "End") "end") (T (il-get "feed" x))))))
      (il-tag-run ename)
    )
    (princ "\nThat is not an ilLumenate run.")
  )
  (il-end)
)

(defun il-scale-text (factor / inches)
  (setq inches (/ 12.0 factor))
  (cond
    ((equal inches 1.0 1e-6) "1\" = 1'-0\"")
    ((equal inches 0.75 1e-6) "3/4\" = 1'-0\"")
    ((equal inches 0.5 1e-6) "1/2\" = 1'-0\"")
    ((equal inches 0.375 1e-6) "3/8\" = 1'-0\"")
    ((equal inches 0.25 1e-6) "1/4\" = 1'-0\"")
    ((equal inches 0.1875 1e-6) "3/16\" = 1'-0\"")
    ((equal inches 0.125 1e-6) "1/8\" = 1'-0\"")
    ((equal inches 0.0625 1e-6) "1/16\" = 1'-0\"")
    (T (strcat "1:" (il-num->str factor 2)))
  )
)

(defun il-piece-of (ename / data center vertices)
  (setq data (entget ename))
  (setq vertices
    (cond
      ((= (cdr (assoc 0 data)) "LINE")
        (list (append (il-xy (cdr (assoc 10 data))) '(0.0)) (append (il-xy (cdr (assoc 11 data))) '(0.0))))
      ((= (cdr (assoc 0 data)) "ARC")
        (il-arc-piece (cdr (assoc 10 data)) (cdr (assoc 40 data)) (cdr (assoc 50 data)) (cdr (assoc 51 data))))
      (T (il-lw-vertices ename))
    )
  )
  (if (and (assoc 210 data) (< (cadddr (assoc 210 data)) 0) (/= (cdr (assoc 0 data)) "LINE"))
    (setq vertices (mapcar '(lambda (v) (list (- (car v)) (cadr v) (- (il-bulge v)))) vertices))
  )
  vertices
)

(defun il-make-lwpolyline (vertices closed like / data)
  (setq data (entget like))
  (entmake (append (list '(0 . "LWPOLYLINE") '(100 . "AcDbEntity") (assoc 8 data))
                   (if (assoc 410 data) (list (assoc 410 data)))
                   (list '(100 . "AcDbPolyline") (cons 90 (length vertices)) (cons 70 (if closed 1 0)))
                   (apply 'append (mapcar '(lambda (v) (list (list 10 (car v) (cadr v)) (cons 42 (il-bulge v)))) vertices))))
  (entlast)
)

(defun il-run-spans (x) (if (il-get "spans" x) (mapcar 'atoi (il-split (il-get "spans" x) ","))))

(defun il-save-run-links (ename breaks spans)
  (il-xupdate ename (list (cons "breaks" (il-join breaks ",")) (cons "spans" (il-join spans ","))))
)

(defun il-run-vertex-at (ename point / vertices target x)
  (setq vertices (il-lw-vertices ename) target (il-jumper-target vertices point (* 0.1 (il-symbol-scale))))
  (if (= (car target) "split")
    (progn
      (setq x (il-xget ename))
      (il-lw-set-vertices ename (il-insert-vertex vertices (cadr target) (caddr target)))
      (il-save-run-links ename (il-shift-breaks (il-run-breaks x) (cadr target)) (il-split-spans (il-run-spans x) (cadr target)))
      (1+ (cadr target))
    )
    (cadr target)
  )
)

(defun il-span-length (vertices spans / total)
  (setq total 0.0)
  (foreach s spans (setq total (+ total (il-segment-length (nth s vertices) (nth (1+ s) vertices) (il-bulge (nth s vertices))))))
  total
)

(defun il-jumper-span (ename first / second a b x spans breaks vertices group low)
  (setq vertices (il-lw-vertices ename) x (il-xget ename) spans (il-run-spans x))
  (setq group (il-span-group spans (il-nearest-segment vertices first)))
  (if (and group (> (distance (il-xy first) (il-xy (nth (il-nearest-vertex ename first) vertices))) (* 0.1 (il-symbol-scale))))
    (progn
      (il-save-run-links ename (il-run-breaks x) (vl-remove-if '(lambda (s) (member s group)) spans))
      (princ (strcat "\n" (il-get "id" x) ": jumper span removed; that stretch counts as tape again."))
    )
    (if (setq second (getpoint first "\nPick where the tape starts again after the gap: "))
      (progn
        (il-run-vertex-at ename first)
        (il-run-vertex-at ename second)
        (setq a (il-nearest-vertex ename first) b (il-nearest-vertex ename second))
        (if (> a b) (setq low b b a a low))
        (if (= a b)
          (princ "\nPick two different points along the run.")
          (progn
            (setq x (il-xget ename) vertices (il-lw-vertices ename) spans (il-run-spans x) breaks (il-run-breaks x) low a)
            (while (< low b) (if (not (member low spans)) (setq spans (cons low spans))) (setq low (1+ low)))
            (setq spans (vl-sort spans '<) breaks (vl-remove-if '(lambda (i) (and (>= i a) (<= i b))) breaks))
            (il-save-run-links ename breaks spans)
            (princ (strcat "\n" (il-get "id" x) ": jumper span of "
                           (il-num->str (il-span-length vertices (il-span-group spans a)) 2)
                           " in. It is jumper cable, not tape, and its drawn length is the jumper's length."))
          )
        )
      )
    )
  )
  (il-tag-run ename)
)

(defun il-tag-index (/ ss index ename owner result pair)
  (if (setq ss (ssget "_X" (list '(0 . "INSERT") (list -3 (list *il-app*)))))
    (progn
      (setq index 0)
      (repeat (sslength ss)
        (setq ename (ssname ss index) index (1+ index) owner (il-get "owner" (il-xget ename)))
        (if owner
          (setq result (if (setq pair (assoc owner result))
                         (subst (cons owner (cons ename (cdr pair))) pair result)
                         (cons (list owner ename) result)))
        )
      )
    )
  )
  result
)

(defun il-run-anchor (run)
  (if (il-get "closed" run) (il-centroid (il-get "vertices" run)) (il-path-point (il-get "vertices" run) 0.5))
)

;; --- Tags ---------------------------------------------------------------------------------------

(defun il-delete-tags (owner-handle)
  (foreach ename (il-owned-tags owner-handle) (entdel ename))
  (if *il-tag-index* (setq *il-tag-index* (vl-remove-if '(lambda (pair) (= (car pair) owner-handle)) *il-tag-index*)))
)

;; (Re)place the run's tag halfway along it with id, style, lengths and part number, and its markers.
;; Feed and jumper markers of RUN, owned by it so ILUPDATE redraws them: the feed at the first vertex
;; (both ends for double-end feeding, halfway along for a centre feed), a jumper at every break.
(defun il-run-markers (run owner / vertices count points)
  (setq vertices (il-get "vertices" run) count (length vertices))
  (setq points (cond ((= (il-get "feed_method" run) "double-end") (list (il-xy (car vertices)) (il-xy (last vertices))))
                     ((= (il-get "feed_method" run) "center") (list (il-path-point vertices 0.5)))
                     (T (list (il-xy (car vertices))))))
  (foreach point points
    (il-xset (il-insert "IL-FEED" (list (car point) (cadr point) 0.0) (il-symbol-scale) "E-LITE-FEED" nil)
             (list (cons "kind" "TAG") (cons "owner" owner)))
  )
  (foreach index (il-get "breaks" run)
    (if (and (> index 0) (< index (1- count)))
      (il-xset (il-insert "IL-JUMPER" (append (il-xy (nth index vertices)) '(0.0)) (il-symbol-scale) "E-LITE-FEED" nil)
               (list (cons "kind" "TAG") (cons "owner" owner)))
    )
  )
  (foreach index (il-get "spans" run)
    (if (< index (1- count))
      (il-xset (il-insert "IL-JUMPER" (append (il-segment-point (nth index vertices) (nth (1+ index) vertices) (il-bulge (nth index vertices)) 0.5) '(0.0))
                          (il-symbol-scale) "E-LITE-FEED" nil)
               (list (cons "kind" "TAG") (cons "owner" owner)))
    )
  )
)

;; Feed and jumper markers placed by toolkit 0.4.2 and earlier had no owner: ILUPDATE redraws them.
(defun il-clear-loose-markers (/ ss index ename)
  (if (setq ss (ssget "_X" '((0 . "INSERT") (2 . "IL-FEED,IL-JUMPER"))))
    (progn
      (setq index 0)
      (repeat (sslength ss)
        (setq ename (ssname ss index) index (1+ index))
        (if (null (il-get "owner" (il-xget ename))) (entdel ename))
      )
    )
  )
)

(defun il-tag-run (ename / run style hint tag)
  (setq run (il-run-from-entity ename) style (il-style-by-id (il-get "style" run)))
  (setq hint (il-run-hint run style (il-catalog)))
  (setq *il-layout* (cdr (assoc 410 (entget ename))))
  (il-delete-tags (il-handle ename))
  (il-run-markers run (il-handle ename))
  (setq tag (il-insert "IL-RUNTAG" (il-run-anchor run) (il-symbol-scale) "E-ANNO-TAGS"
              (list (cons "TAG" (il-get "id" run))
                    (cons "STYLE" (if style (il-style-label style) "no style"))
                    (cons "LENGTH" (if (il-get "server_in" run)
                                     (strcat (il-num->str (il-get "server_in" run) 2) " in built")
                                     (il-hint-text hint)))
                    (cons "PART" (il-get "part_number" run)))))
  (il-xset tag (list (cons "kind" "TAG") (cons "owner" (il-handle ename))))
  (setq *il-layout* nil)
  tag
)

;; --- Copies and symbol scale ------------------------------------------------------------------

;; Kinds that carry an id, and the attribute that shows it (on the entity when it is a block, else
;; on the tag it owns). Run tags are redrawn by il-tag-run, so runs need none.
(setq *il-copy-kinds* '(("RUN" nil) ("ROOM" "ID") ("WIRE" "TAG") ("CABINET" "TAG") ("PSU" "TAG") ("CONTROL" "TAG")))

;; What a copy must not inherit: the portal line its original was imported as, the runs a PSU
;; feeds, a fixed DMX address.
(setq *il-copy-resets*
  '(("RUN" ("line_key") ("configured_name") ("config_hash") ("part_number") ("server_in") ("feed_handles"))
    ("PSU" ("runs"))
    ("CONTROL" ("start" . "auto"))))

;; Where an entity sits: a block's insertion point, a polyline's centroid.
(defun il-ref-point (ename / data)
  (setq data (entget ename))
  (if (= (cdr (assoc 0 data)) "INSERT") (cdr (assoc 10 data)) (il-centroid (il-lw-vertices ename)))
)

(defun il-owned-tags (owner-handle / ss index ename result)
  (if *il-tag-index*
    (vl-remove-if-not '(lambda (e) (entget e)) (cdr (assoc owner-handle *il-tag-index*)))
    (progn
      (if (setq ss (ssget "_X" (list '(0 . "INSERT") (list -3 (list *il-app*)))))
        (progn
          (setq index 0)
          (repeat (sslength ss)
            (setq ename (ssname ss index) index (1+ index))
            (if (= (il-get "owner" (il-xget ename)) owner-handle) (setq result (cons ename result)))
          )
        )
      )
      result
    )
  )
)

;; Tags copied with an entity still name the original as owner: give the copy the ones nearer to it.
(defun il-adopt-tags (original copy attribute id / here there point)
  (setq here (il-ref-point copy) there (il-ref-point original))
  (foreach tag (il-owned-tags (il-handle original))
    (setq point (cdr (assoc 10 (entget tag))))
    (if (< (distance point here) (distance point there))
      (progn
        (il-xupdate tag (list (cons "owner" (il-handle copy))))
        (if attribute (il-set-attribute tag attribute id))
      )
    )
  )
)

;; COPY, ARRAY and paste duplicate XData, id included. Give every copy its own id, drop what it must
;; not inherit, and record each entity's own handle ("self") so later copies are told apart.
(defun il-fix-copies (verbose / kind attribute enames x records copy original old id block-p)
  (foreach row *il-copy-kinds*
    (setq kind (car row) attribute (cadr row) enames (il-entities kind) records nil)
    (foreach ename enames
      (setq x (il-xget ename))
      (setq records (cons (list ename (il-get "id" x) (il-get "self" x) (il-handle ename)) records))
    )
    (foreach pair (il-copies (reverse records))
      (setq copy (car pair) original (handent (cdr pair)) old (il-get "id" (il-xget copy)))
      (setq id (il-next-id kind (il-id-prefix old)) block-p (= (cdr (assoc 0 (entget copy))) "INSERT"))
      (il-xupdate copy (cons (cons "id" id) (cdr (assoc kind *il-copy-resets*))))
      (if (and attribute block-p) (il-set-attribute copy attribute id))
      (if original (il-adopt-tags original copy (if block-p nil attribute) id))
      (if verbose (princ (strcat "\nCopy of " old " is now " id ".")))
    )
    (foreach ename enames
      (if (/= (il-get "self" (il-xget ename)) (il-handle ename))
        (il-xupdate ename (list (cons "self" (il-handle ename))))
      )
    )
  )
)

;; Resize every placed toolkit symbol by FACTOR about its insertion point; title blocks stay 1:1.
(defun il-rescale-symbols (factor / ss index ename data base next count)
  (setq count 0)
  (if (setq ss (ssget "_X" '((0 . "INSERT") (2 . "IL-*"))))
    (progn
      (setq index 0)
      (repeat (sslength ss)
        (setq ename (ssname ss index) index (1+ index) data (entget ename))
        (if (not (il-starts-with (cdr (assoc 2 data)) "IL-TB-"))
          (progn
            (setq base (cdr (assoc 10 data)))
            (foreach code '(41 42 43)
              (if (assoc code data) (setq data (subst (cons code (* factor (cdr (assoc code data)))) (assoc code data) data)))
            )
            (entmod data)
            (setq next (entnext ename))
            (while (and next (= (cdr (assoc 0 (setq data (entget next)))) "ATTRIB"))
              (setq data (subst (cons 10 (il-scale-about base (cdr (assoc 10 data)) factor)) (assoc 10 data) data))
              (if (and (assoc 11 data) (or (/= 0 (il-num-or-0 (cdr (assoc 72 data)))) (/= 0 (il-num-or-0 (cdr (assoc 74 data))))))
                (setq data (subst (cons 11 (il-scale-about base (cdr (assoc 11 data)) factor)) (assoc 11 data) data))
              )
              (setq data (subst (cons 40 (* factor (cdr (assoc 40 data)))) (assoc 40 data) data))
              (entmod data)
              (setq next (entnext next))
            )
            (entupd ename)
            (setq count (1+ count))
          )
        )
      )
    )
  )
  count
)

(defun il-num-or-0 (value) (if (numberp value) value 0))

;; --- Site: ILSCALE, ILROOM, ILCAB, ILPSU, ILCONNECT, ILWIRE --------------------------------------

(defun c:ILSCALE (/ ss first second measured actual factor)
  (il-begin)
  (princ "\nSelect the underlay to calibrate (PDF underlay, image or xref).")
  (if (and (setq ss (ssget))
           (setq first (getpoint "\nFirst point of a known dimension: "))
           (setq second (getpoint first "\nSecond point: ")))
    (progn
      (setq measured (distance first second))
      (if (< measured 1e-6)
        (princ "\nThose are the same point. Pick both ends of a dimension you know.")
        (progn
          (initget 6)
          (setq actual (getdist "\nTrue length of that dimension (inches, or feet with ', for example 12'6\"): "))
          (if actual
            (progn
              (setq factor (/ actual measured))
              (command "_.SCALE" ss "" "_non" first factor)
              (il-set-setting "scale_verified" 'IL-TRUE)
              (princ (strcat "\nScaled by " (il-num->str factor 6) ". Scale verified."))
            )
          )
        )
      )
    )
  )
  (il-end)
)

(defun il-room-slug (name)
  (strcat "Z-" (il-replace-all (il-replace-all (il-trim name) " " "-") "/" "-"))
)

(defun c:ILROOM (/ picked ename point before name level env id x other)
  (il-begin)
  (il-assets-ensure)
  (initget "Pick")
  (setq picked (entsel "\nSelect the room's closed polyline, or [Pick a point inside]: "))
  (cond
    ((= picked "Pick")
      (if (setq point (getpoint "\nPoint inside the room: "))
        (progn
          (setq before (entlast))
          (command "_.-BOUNDARY" "_Advanced" "_Object" "_Polyline" "" "_non" point "")
          (if (not (equal before (entlast))) (setq ename (entlast)))
        )
      )
    )
    ((and (listp picked) picked (il-kind (car picked)) (/= (il-kind (car picked)) "ROOM"))
      (princ (strcat "\nThat is an ilLumenate " (il-kind (car picked)) ", not a room outline.")))
    ((and (listp picked) picked (= (cdr (assoc 0 (entget (car picked)))) "LWPOLYLINE") (il-lw-closed (car picked)))
      (setq ename (car picked)))
  )
  (if ename
    (progn
      (setq x (il-xget ename))
      (setq name (il-trim (il-ask "Room name" (if (il-get "name" x) (il-get "name" x) "Room"))))
      (if (= name "") (setq name "Room"))
      (setq level (il-ask "Level" (if (il-get "level" x) (il-get "level" x) "L1")))
      (setq env (il-choose "Environment" *il-env-choices*
                           (if (vl-position (il-get "env" x) *il-env-choices*) (1+ (vl-position (il-get "env" x) *il-env-choices*)) 1)))
      (setq id (il-room-slug name))
      (if (and (setq other (il-find-id "ROOM" id)) (not (equal other ename)))
        (progn (setq id (il-next-id "ROOM" (strcat id "-"))) (princ (strcat "\nAnother room is already " (il-room-slug name) "; this one is " id ".")))
      )
      (entmod (subst (cons 8 "E-ANNO-ROOM") (assoc 8 (entget ename)) (entget ename)))
      (il-xset ename (list (cons "kind" "ROOM") (cons "id" id) (cons "name" name) (cons "level" level) (cons "env" env)
                           (cons "self" (il-handle ename))))
      (setq *il-layout* (cdr (assoc 410 (entget ename))))
      (il-delete-tags (il-handle ename))
      (il-xset (il-insert "IL-ROOMTAG" (il-centroid (il-lw-vertices ename)) (il-symbol-scale) "E-ANNO-ROOM"
                 (list (cons "NAME" name) (cons "ID" id) (cons "ENV" env)))
               (list (cons "kind" "TAG") (cons "owner" (il-handle ename))))
      (setq *il-layout* nil)
      (princ (strcat "\nRoom " id " (" env "). Runs and equipment inside it pick it up on ILUPDATE."))
    )
    (if (not (and (listp picked) picked (il-kind (car picked)))) (princ "\nNo closed polyline."))
  )
  (il-end)
)

;; The room containing POINT, as its id.
(defun il-room-at (point / found x)
  (foreach ename (il-entities "ROOM")
    (if (and (null found) (il-point-in-polygon point (il-lw-vertices ename)))
      (setq found (il-get "id" (il-xget ename)))
    )
  )
  found
)

(defun c:ILCAB (/ point id rating note insert)
  (il-begin)
  (il-assets-ensure)
  (if (setq point (getpoint "\nCabinet or PSU location: "))
    (progn
      (setq id (il-ask-id "CABINET" "Cabinet tag" "CAB-"))
      (initget "Dry Damp Wet")
      (setq rating (getkword "\nLocation rating [Dry/Damp/Wet] <Dry>: "))
      (setq note (il-ask "Access note" ""))
      (setq insert (il-insert "IL-CABINET" point (il-symbol-scale) "E-POWR-CABN"
                     (list (cons "TAG" id) (cons "RATING" (if rating rating "Dry")) (cons "ACCESS" note))))
      (il-xset insert (list (cons "kind" "CABINET") (cons "id" id) (cons "room" (il-room-at point))
                            (cons "rating" (if rating rating "Dry")) (cons "access" note) (cons "self" (il-handle insert))))
      (princ (strcat "\nCabinet " id "."))
    )
  )
  (il-end)
)

(defun il-nearest (kind point / best best-distance d)
  (foreach ename (il-entities kind)
    (setq d (distance (cdr (assoc 10 (entget ename))) point))
    (if (or (null best-distance) (< d best-distance)) (setq best ename best-distance d))
  )
  best
)

(defun c:ILPSU (/ point id cabinet drivers names model insert)
  (il-begin)
  (il-assets-ensure)
  (if (setq point (getpoint "\nPSU location: "))
    (progn
      (setq id (il-ask-id "PSU" "PSU tag" "PS-"))
      (setq cabinet (il-cabinet-for point))
      (setq drivers (if (il-catalog) (il-items (il-j (il-catalog) "drivers"))))
      (setq names (cons "Choose in the System Designer"
                        (mapcar '(lambda (d) (strcat (il-str (il-j d "code")) "  "
                                                     (if (il-number (il-j d "rated_w")) (strcat (il-num->str (il-number (il-j d "rated_w")) 0) " W") "rating unknown")))
                                drivers)))
      (setq model (il-choose "Model (optional; the System Designer sizes and assigns)" names 1))
      (if (= model "Choose in the System Designer") (setq model nil) (if model (setq model (car (il-split model "  ")))))
      (setq insert (il-insert "IL-PSUTAG" point (il-symbol-scale) "E-POWR-EQPM" (list (cons "TAG" id) (cons "MODEL" model))))
      (il-xset insert (list (cons "kind" "PSU") (cons "id" id)
                            (cons "cabinet" (if cabinet (il-get "id" (il-xget cabinet))))
                            (cons "item_code" model) (cons "self" (il-handle insert))))
      (princ (strcat "\nPSU " id (if cabinet (strcat " in " (il-get "id" (il-xget cabinet))) "") ". Connect runs with ILCONNECT."))
    )
  )
  (il-end)
)

(defun c:ILCONNECT (/ picked psu x runs ss index ename cabinet action id moved others other-runs)
  (il-begin)
  (if (and (setq picked (entsel "\nPick the PSU: ")) (= (il-kind (setq psu (car picked))) "PSU"))
    (progn
      (setq x (il-xget psu) runs (if (il-get "runs" x) (il-split (il-get "runs" x) ",")) cabinet (il-get "cabinet" x))
      (initget "Add Remove")
      (setq action (getkword (strcat "\n" (il-get "id" x) " feeds " (if runs (il-join runs ", ") "nothing yet") ". [Add runs/Remove runs] <Add>: ")))
      (princ (if (= action "Remove") "\nSelect the runs to take off it." "\nSelect the runs it feeds."))
      (if (setq ss (ssget '((0 . "LWPOLYLINE"))))
        (progn
          (setq index 0)
          (repeat (sslength ss)
            (setq ename (ssname ss index) index (1+ index) id (il-get "id" (il-xget ename)))
            (if (and (= (il-kind ename) "RUN") id)
              (if (= action "Remove")
                (setq runs (vl-remove id runs))
                (progn
                  (if (not (member id runs)) (setq runs (append runs (list id))))
                  (if cabinet (il-xupdate ename (list (cons "cabinet" cabinet))))
                  ;; A run has one supply: take it off any other PSU.
                  (foreach other (il-entities "PSU")
                    (if (and (not (equal other psu))
                             (member id (setq other-runs (if (il-get "runs" (il-xget other)) (il-split (il-get "runs" (il-xget other)) ",")))))
                      (progn
                        (il-xupdate other (list (cons "runs" (il-join (vl-remove id other-runs) ","))))
                        (setq moved (cons (strcat id " from " (il-get "id" (il-xget other))) moved))
                        (if (not (member other others)) (setq others (cons other others)))
                      )
                    )
                  )
                )
              )
            )
          )
          (il-xupdate psu (list (cons "runs" (il-join runs ","))))
          (princ (strcat "\n" (il-get "id" x) " feeds " (if runs (il-join runs ", ") "nothing") "."))
          (if moved (princ (strcat "\nMoved " (il-join (reverse moved) ", ") ".")))
          (foreach other (cons psu others) (il-update-psu-tag other))
        )
      )
    )
    (princ "\nThat is not an ilLumenate PSU.")
  )
  (il-end)
)

(defun il-end-id (ename / kind)
  (setq kind (il-kind ename))
  (if (member kind '("RUN" "PSU" "CABINET" "CONTROL")) (il-get "id" (il-xget ename)))
)

(defun c:ILWIRE (/ from to kind before ename id layer wire-length)
  (il-begin)
  (il-assets-ensure)
  (if (setq from (il-pick-end "\nPick where the wire starts (PSU, cabinet, control or run): "))
    (progn
      (initget "Lv Line Data")
      (setq kind (getkword "\nWire [Lv class 2/Line voltage/Data] <Lv>: "))
      (setq kind (cond ((= kind "Line") "line") ((= kind "Data") "data") (T "lv")))
      (setq layer (cond ((= kind "line") "E-POWR-WIRE-LINE") ((= kind "data") "E-LITE-DATA") (T "E-LITE-WIRE-CL2")))
      (setvar "CLAYER" layer)
      (princ "\nDraw the wire's path. Press Enter to finish.")
      (setq before (entlast))
      (command "_.PLINE")
      (while (> (getvar "CMDACTIVE") 0) (command pause))
      (setq ename (entlast))
      (cond
        ((or (equal before ename) (/= (cdr (assoc 0 (entget ename))) "LWPOLYLINE")) (princ "\nNo wire drawn."))
        ((null (setq to (il-pick-end "\nPick where the wire ends (PSU, cabinet, control or run): ")))
          (princ "\nThe path is drawn but not recorded as a wire. Erase it, or run ILWIRE again and draw over it."))
        (T
          (setq id (il-next-id "WIRE" "W-"))
          (il-xset ename (list (cons "kind" "WIRE") (cons "id" id) (cons "from" from) (cons "to" to) (cons "wire" kind) (cons "self" (il-handle ename))))
          (setq wire-length (il-get "length_in" (il-path-length (il-lw-vertices ename) nil)))
          (il-tag-wire ename)
          (princ (strcat "\n" id ": " from " to " to ", " (il-num->str (/ wire-length 12.0) 1) " ft path (slack and waste are added in the System Designer)."))
        )
      )
    )
    (princ "\nPick a PSU, cabinet, control or run.")
  )
  (il-end)
)

(defun il-cabinet-for (point / near picked)
  (setq near (il-nearest "CABINET" point))
  (cond
    ((and near (<= (distance (il-xy (cdr (assoc 10 (entget near)))) (il-xy point)) (* 1.5 (il-symbol-scale)))) near)
    ((il-entities "CABINET")
      (setq picked (entsel "\nNot at a cabinet. Pick the cabinet it goes in, or press Enter for none: "))
      (if (and picked (= (il-kind (car picked)) "CABINET")) (car picked)))
  )
)

(defun il-pick-end (message / picked id done)
  (while (not done)
    (setq picked (entsel message))
    (cond
      ((null picked) (setq done T))
      ((setq id (il-end-id (car picked))) (setq done T))
      (T (princ "\nThat is not a PSU, cabinet, control or run; pick again, or press Enter to stop."))
    )
  )
  id
)

(defun il-tag-wire (ename / x wire-length text tags)
  (setq x (il-xget ename) wire-length (il-get "length_in" (il-path-length (il-lw-vertices ename) nil)))
  (setq text (strcat (il-num->str (/ wire-length 12.0) 1) "'") tags (il-owned-tags (il-handle ename)))
  (if tags
    (foreach tag tags (il-set-attribute tag "LENGTH" text) (il-set-attribute tag "TAG" (il-get "id" x)))
    (progn
      (setq *il-layout* (cdr (assoc 410 (entget ename))))
      (il-xset (il-insert "IL-WIRETAG" (il-path-point (il-lw-vertices ename) 0.5) (il-symbol-scale) "E-ANNO-TAGS"
                 (list (cons "TAG" (il-get "id" x)) (cons "LENGTH" text)))
               (list (cons "kind" "TAG") (cons "owner" (il-handle ename))))
      (setq *il-layout* nil)
    )
  )
)

(defun il-update-psu-tag-in (psu model / x loads hint driver result)
  (setq x (il-xget psu))
  (foreach run (il-get "runs" model)
    (if (member (il-get "id" run) (if (il-get "runs" x) (il-split (il-get "runs" x) ",")))
      (if (il-get "watts" (setq hint (il-run-hint run (il-model-style model (il-get "style" run)) (il-catalog))))
        (setq loads (cons (il-get "watts" hint) loads))
      )
    )
  )
  (foreach item (if (il-catalog) (il-items (il-j (il-catalog) "drivers")))
    (if (= (il-j item "code") (il-get "item_code" x)) (setq driver item))
  )
  (if (and driver (il-number (il-j driver "rated_w")))
    (progn
      (setq result (il-psu-load loads (il-number (il-j driver "rated_w")) (il-j driver "usable_load_factor")))
      (il-set-attribute psu "LOAD" (strcat (il-num->str (il-get "total_w" result) 1) " W  " (il-num->str (il-get "pct_of_usable" result) 0) "%"))
    )
    (il-set-attribute psu "LOAD" (strcat (il-num->str (il-sum loads) 1) " W"))
  )
)

(defun il-rooms-index ()
  (mapcar '(lambda (ename) (cons (il-get "id" (il-xget ename)) (cons (il-get "name" (il-xget ename)) (il-lw-vertices ename))))
          (il-entities "ROOM"))
)

(defun il-room-in (rooms point / found)
  (foreach room rooms
    (if (and (null found) (il-point-in-polygon point (cddr room))) (setq found room))
  )
  found
)

(defun il-prune-links (/ ids x kept zones changed)
  (setq ids (mapcar '(lambda (e) (il-get "id" (il-xget e))) (il-entities "RUN")))
  (foreach psu (il-entities "PSU")
    (setq x (il-xget psu))
    (if (il-get "runs" x)
      (progn
        (setq kept (vl-remove-if-not '(lambda (id) (member id ids)) (il-split (il-get "runs" x) ",")))
        (if (/= (length kept) (length (il-split (il-get "runs" x) ","))) (il-xupdate psu (list (cons "runs" (il-join kept ",")))))
      )
    )
  )
  (setq zones (mapcar '(lambda (zone / runs)
                         (setq runs (il-items (il-j zone "runs")))
                         (if (vl-some '(lambda (id) (not (member id ids))) runs) (setq changed T))
                         (il-jset zone "runs" (il-arr (vl-remove-if-not '(lambda (id) (member id ids)) runs))))
                      (il-zones)))
  (if changed (il-store-json "ZONES" (il-arr zones)))
)

(defun il-worst-severity (issues ref overrides / worst)
  (foreach issue issues
    (if (and (= (il-get "ref" issue) ref) (not (il-overridden-p issue overrides)))
      (cond
        ((= (il-get "severity" issue) "error") (setq worst "error"))
        ((and (= (il-get "severity" issue) "warning") (/= worst "error")) (setq worst "warning"))
      )
    )
  )
  worst
)

(defun il-next-zone-id (zones / number)
  (setq number 1)
  (while (vl-some '(lambda (z) (= (il-j z "id") (strcat "ZN-" (itoa number)))) zones) (setq number (1+ number)))
  (strcat "ZN-" (itoa number))
)

(defun il-num-text (value digits) (if (il-number value) (il-num->str (il-number value) digits) ""))

;; --- Other lines and overrides ----------------------------------------------------------------

(defun c:ILOTHER (/ others fixture-type qty maker model watts action)
  (il-begin)
  (setq others (il-items (il-fetch-json "OTHERS")))
  (if others
    (princ (strcat "\nOther-manufacturer lines: " (il-join (mapcar '(lambda (o) (strcat (il-str (il-j o "fixture_type")) " x" (il-str (il-j o "qty")))) others) ", ")))
  )
  (setq fixture-type (il-trim (il-ask "Schedule Type of the other manufacturer's fixture" "X1")))
  (if (vl-some '(lambda (o) (= (il-j o "fixture_type") fixture-type)) others)
    (progn
      (initget "Replace Delete")
      (setq action (getkword (strcat "\n" fixture-type " is already in this drawing. [Replace/Delete] <Replace>: ")))
    )
  )
  (setq others (vl-remove-if '(lambda (o) (= (il-j o "fixture_type") fixture-type)) others))
  (if (= action "Delete")
    (princ (strcat "\n" fixture-type " removed."))
    (progn
      (initget 7)
      (setq qty (getint "\nQuantity: "))
      (setq maker (il-ask "Manufacturer" "") model (il-ask "Model" ""))
      (initget 4)
      (setq watts (getreal "\nWatts each (for the System Designer, Enter to skip): "))
      (setq others (append others (list (il-obj (append (list (cons "fixture_type" fixture-type) (cons "qty" qty) (cons "manufacturer_name" maker))
                                                        (if (/= model "") (list (cons "fixture_model_number" model)))
                                                        (if watts (list (cons "watts_each" watts))))))))
    )
  )
  (il-store-json "OTHERS" (il-arr others))
  (princ (strcat "\n" (itoa (length others)) " other-manufacturer lines in this drawing."))
  (il-end)
)

(defun il-overrides () (il-items (il-fetch-json "OVERRIDES")))

(defun il-add-override (code ref note / kept)
  (foreach item (il-overrides)
    (if (not (and (= (il-j item "code") code) (= (il-j item "ref") ref))) (setq kept (cons item kept)))
  )
  (il-store-json "OVERRIDES" (il-arr (cons (il-obj (list (cons "code" code) (cons "ref" ref) (cons "note" note))) (reverse kept))))
)

(defun c:ILOVERRIDE (/ issues names choice issue note overrides action)
  (il-begin)
  (setq overrides (il-overrides))
  (if overrides
    (progn
      (initget "Add Remove")
      (setq action (getkword (strcat "\n" (itoa (length overrides)) " checks are overridden. [Add an override/Remove one] <Add>: ")))
    )
  )
  (if (= action "Remove")
    (progn
      (setq names (mapcar '(lambda (o) (strcat (il-str (il-j o "code")) " " (il-str (il-j o "ref")) ": " (il-str (il-j o "note")))) overrides))
      (if (setq choice (il-choose "Remove which override" names nil))
        (progn
          (setq issue (nth (vl-position choice names) overrides))
          (il-store-json "OVERRIDES" (il-arr (vl-remove-if '(lambda (o) (and (= (il-j o "code") (il-j issue "code")) (= (il-j o "ref") (il-j issue "ref")))) overrides)))
          (princ "\nOverride removed.")
        )
      )
    )
    (progn
      (il-update-all nil)
      (setq issues (vl-remove-if '(lambda (i) (or (= (il-get "severity" i) "info") (il-overridden-p i (il-get "overrides" (il-model)))))
                                 (il-check (il-model) (il-catalog) (il-today))))
      (if (null issues)
        (princ "\nNothing to override: no open errors or warnings.")
        (progn
          (setq names (mapcar '(lambda (i) (strcat (il-get "code" i) " " (il-str (il-get "ref" i)) ": " (il-get "text" i))) issues))
          (if (setq choice (il-choose "Override which check" names nil))
            (progn
              (setq issue (nth (vl-position choice names) issues) note (il-trim (il-ask "Reason (kept with the quote)" "")))
              (if (>= (strlen note) 3)
                (progn (il-add-override (il-get "code" issue) (il-get "ref" issue) note) (princ "\nOverride recorded."))
                (princ "\nGive a reason of at least 3 characters.")
              )
            )
          )
        )
      )
    )
  )
  (il-end)
)

;; --- Model, ILUPDATE, ILCHECK ------------------------------------------------------------------

(defun il-rev (/ value)
  (setq value (il-number (il-setting "rev")))
  (if value (fix value) 0)
)

(defun il-model (/ runs rooms cabinets psus wires controls x drawing)
  (foreach ename (il-entities "ROOM")
    (setq x (il-xget ename))
    (setq rooms (cons (list (cons "id" (il-get "id" x)) (cons "name" (il-get "name" x)) (cons "level" (il-get "level" x)) (cons "env" (il-get "env" x))) rooms))
  )
  (foreach ename (il-entities "RUN") (setq runs (cons (il-run-from-entity ename) runs)))
  (foreach ename (il-entities "CABINET")
    (setq x (il-xget ename))
    (setq cabinets (cons (list (cons "id" (il-get "id" x)) (cons "room" (il-get "room" x)) (cons "location_rating" (il-get "rating" x)) (cons "access_note" (il-get "access" x))) cabinets))
  )
  (foreach ename (il-entities "PSU")
    (setq x (il-xget ename))
    (setq psus (cons (list (cons "id" (il-get "id" x)) (cons "cabinet" (il-get "cabinet" x)) (cons "item_code" (il-get "item_code" x))
                           (cons "runs" (if (il-get "runs" x) (il-split (il-get "runs" x) ","))))
                     psus))
  )
  (foreach ename (il-entities "WIRE")
    (setq x (il-xget ename))
    (setq wires (cons (list (cons "id" (il-get "id" x)) (cons "from" (il-get "from" x)) (cons "to" (il-get "to" x)) (cons "kind" (il-get "wire" x))
                            (cons "length_in" (il-get "length_in" (il-path-length (il-lw-vertices ename) nil))))
                      wires))
  )
  (foreach ename (il-entities "CONTROL")
    (setq x (il-xget ename))
    (setq controls (cons (list (cons "id" (il-get "id" x)) (cons "handle" (il-handle ename)) (cons "item_code" (il-get "item_code" x))
                               (cons "cabinet" (il-get "cabinet" x)) (cons "room" (il-get "room" x))
                               (cons "universe" (if (il-get "universe" x) (atoi (il-get "universe" x))))
                               (cons "start" (if (and (il-get "start" x) (/= (il-get "start" x) "auto")) (atoi (il-get "start" x)) "auto"))
                               (cons "control_from" (il-get "control_from" x)) (cons "notes" (il-get "notes" x))
                               (cons "line_key" (il-get "line_key" x)))
                         controls))
  )
  (setq drawing (list (cons "file" (getvar "DWGNAME")) (cons "rev" (il-rev))
                      (cons "scale_verified" (il-true-p (il-setting "scale_verified")))
                      (cons "schedule" (il-setting "schedule")) (cons "project" (il-setting "project"))
                      (cons "schedule_version" (il-setting "schedule_version"))))
  (list
    (cons "drawing" drawing)
    (cons "rooms" (reverse rooms))
    (cons "cabinets" (reverse cabinets))
    (cons "runs" (vl-sort (reverse runs) '(lambda (a b) (< (il-str (il-get "id" a)) (il-str (il-get "id" b))))))
    (cons "styles" (il-styles))
    (cons "psus" (reverse psus))
    (cons "wires" (reverse wires))
    (cons "controls" (vl-sort (reverse controls) '(lambda (a b) (< (il-str (il-get "id" a)) (il-str (il-get "id" b))))))
    (cons "zones" (mapcar '(lambda (zone)
                             (list (cons "id" (il-j zone "id")) (cons "name" (il-j zone "name")) (cons "method" (il-j zone "method"))
                                   (cons "control" (il-j zone "control")) (cons "port" (il-j zone "port"))
                                   (cons "runs" (il-items (il-j zone "runs")))))
                          (il-zones)))
    (cons "others" (il-items (il-fetch-json "OTHERS")))
    (cons "overrides" (mapcar '(lambda (o) (list (cons "code" (il-j o "code")) (cons "ref" (il-j o "ref")) (cons "note" (il-j o "note")))) (il-overrides)))
  )
)

;; The drawing's content hash: what was drawn, not when or by whom.
(defun il-model-hash (model catalog / package)
  (setq package (il-package model catalog nil "hash"))
  (il-sha256 (il-json-text (il-obj (vl-remove-if '(lambda (pair) (member (car pair) '("toolkit" "drawing" "check" "catalog"))) (cdr package)))))
)

(defun il-update-psu-tag (psu) (il-update-psu-tag-in psu (il-model)))

(defun c:ILUPDATE () (il-begin) (il-update-all T) (il-end))

;; New ids for copies and runs without one, rooms by position, tags and PSU loads.
(defun il-update-all (verbose / x id room count moved model rooms)
  (il-fix-copies verbose)
  (il-clear-loose-markers)
  (setq moved (il-recenter-tags))
  (if (and verbose (> moved 0)) (princ (strcat "\n" (itoa moved) " tag labels centred.")))
  (setq *il-tag-index* (il-tag-index) rooms (il-rooms-index) count 0)
  (foreach ename (il-entities "RUN")
    (setq x (il-xget ename) id (il-get "id" x))
    (if (or (null id) (= id ""))
      (il-xupdate ename (list (cons "id" (il-next-id "RUN" (strcat (if (il-get "type" x) (il-get "type" x) "L") "-")))))
    )
    (setq room (il-room-in rooms (il-run-anchor (il-run-from-entity ename))))
    (if (/= (car room) (il-get "room" x))
      (il-xupdate ename (list (cons "room" (car room)) (cons "location" (cadr room))))
    )
    (il-tag-run ename)
    (setq count (1+ count))
  )
  (foreach kind '("CABINET" "CONTROL")
    (foreach ename (il-entities kind)
      (setq room (il-room-in rooms (cdr (assoc 10 (entget ename)))))
      (if (/= (car room) (il-get "room" (il-xget ename))) (il-xupdate ename (list (cons "room" (car room)))))
    )
  )
  (il-prune-links)
  (foreach ename (il-entities "WIRE") (il-tag-wire ename))
  (setq model (il-model))
  (foreach psu (il-entities "PSU") (il-update-psu-tag-in psu model))
  (setq *il-tag-index* nil)
  (if verbose (princ (strcat "\n" (itoa count) " runs updated.")))
  count
)

(defun il-clear-markers (/ ss)
  (if (setq ss (ssget "_X" '((0 . "INSERT") (2 . "IL-ISSUE"))))
    (command "_.ERASE" ss "")
  )
)

(defun c:ILCHECK (/ model issues counts ename overrides last-hash x)
  (il-begin)
  (il-assets-ensure)
  (il-update-all nil)
  (setq model (il-model) overrides (il-get "overrides" model))
  (setq issues (il-check model (il-catalog) (il-today)))
  (setq last-hash (il-setting "receipt_hash"))
  (if (and last-hash (il-catalog) (/= last-hash (il-model-hash model (il-catalog))))
    (setq issues (append issues (list (il-issue "DRAWING_CHANGED_SINCE_IMPORT" "drawing" "info" "The drawing changed since its last import; run ILQUOTE and import it again"))))
  )
  (il-clear-markers)
  (foreach issue issues
    (princ (strcat "\n" (strcase (il-get "severity" issue)) " " (il-get "code" issue) " " (il-str (il-get "ref" issue)) ": " (il-get "text" issue)
                   (if (il-overridden-p issue overrides) " [overridden]" "")))
    (if (and (/= (il-get "severity" issue) "info") (setq ename (il-find-id "RUN" (il-get "ref" issue))))
      (progn
        (setq *il-layout* (cdr (assoc 410 (entget ename))))
        (il-insert "IL-ISSUE" (il-run-anchor (il-run-from-entity ename)) (il-symbol-scale) "E-ANNO-ISSU" (list (cons "CODE" (il-get "code" issue))))
        (setq *il-layout* nil)
      )
    )
  )
  ;; Red for an open error, yellow for a warning, green when clean (ByLayer once imported).
  (foreach ename (il-entities "RUN")
    (setq x (il-xget ename))
    (il-color-run ename (cond ((il-worst-severity issues (il-get "id" x) overrides))
                              ((il-get "line_key" x) "imported")
                              (T "ok")))
  )
  (setq counts (il-issue-counts issues overrides))
  (princ (strcat "\nILCHECK: " (itoa (car counts)) " errors, " (itoa (cadr counts)) " warnings"
                 (if (> (car counts) 0) ". Fix or override (ILOVERRIDE) the errors before ILQUOTE." ".")))
  (il-end)
)

;; --- ILQUOTE and ILRECEIPT ----------------------------------------------------------------------

(defun c:ILQUOTE (/ catalog model issues counts package hash path rev)
  (il-begin)
  (setq catalog (il-require-catalog))
  (il-update-all nil)
  (setq rev (1+ (il-rev)))
  (setq model (il-model) issues (il-check model catalog (il-today)) counts (il-issue-counts issues (il-get "overrides" model)))
  (setq hash (il-model-hash model catalog))
  (setq model (il-put "drawing" (il-put "rev" rev (il-put "hash" (strcat "sha256:" hash) (il-get "drawing" model))) model))
  (setq package (il-package model catalog issues (il-platform)))
  (setq path (getfiled "Save the drawing package" (strcat (getvar "DWGPREFIX") (vl-filename-base (getvar "DWGNAME")) ".ilq") "json" 1))
  (cond
    ((null path) (princ "\nNo package written."))
    ((not (il-json-write-file package path)) (princ (strcat "\nCould not write " path ". Is it open in another program, or the folder read-only?")))
    (T
      (il-set-setting "rev" rev)
      (il-set-setting "last_package_hash" hash)
      (princ (strcat "\nWrote " path " (revision " (itoa rev) "): " (itoa (length (il-get "runs" model))) " runs, "
                     (itoa (length (il-get "rooms" model))) " rooms, " (itoa (length (il-get "psus" model))) " PSUs, "
                     (itoa (length (il-get "wires" model))) " wires; " (itoa (car counts)) " errors, " (itoa (cadr counts)) " warnings."))
      (if (> (car counts) 0) (princ "\nThe portal refuses packages with errors: run ILCHECK, then fix or override them."))
      (princ "\nUpload it on the schedule page: Import Drawing. No prices are in the package.")
    )
  )
  (il-end)
)

(defun c:ILRECEIPT (/ path receipt index count ename run)
  (il-begin)
  (setq path (getfiled "Import receipt from the portal" (getvar "DWGPREFIX") "json" 0))
  (cond
    ((null path))
    ((null (setq receipt (il-json-read-file path))) (princ (strcat "\nCould not read the receipt: " (il-str *il-jr-error*))))
    ((null (setq index (il-receipt-index receipt))) (princ "\nThis is not an ilLumenate import receipt."))
    (T
      (setq count 0)
      (foreach ename (il-entities "RUN")
        (setq run (il-run-with-receipt (il-run-from-entity ename) index))
        (if (il-get "line_key" run)
          (progn
            (il-xupdate ename (mapcar '(lambda (key) (cons key (il-str (il-get key run))))
                                      '("line_key" "configured_name" "config_hash" "part_number" "server_in")))
            (entmod (subst '(62 . 256) (assoc 62 (entget ename)) (entget ename)))
            (il-tag-run ename)
            (setq count (1+ count))
          )
        )
      )
      (foreach pair (il-receipt-controls receipt)
        (if (and (cdr pair) (setq ename (il-find-id "CONTROL" (car pair))))
          (il-xupdate ename (list (cons "line_key" (cdr pair))))
        )
      )
      (il-set-setting "schedule" (il-j receipt "schedule"))
      (il-set-setting "schedule_version" (il-j receipt "schedule_version"))
      (il-set-setting "receipt_hash" (substr (il-str (il-jp receipt '("drawing" "hash"))) 8))
      (il-store-json "RECEIPT" receipt)
      (princ (strcat "\n" (itoa count) " runs stamped with their schedule lines (" (il-str (il-j receipt "import")) ")."))
    )
  )
  (il-end)
)

;; --- Controls in v1: ILCTRL, ILZONE, ILDMX (PRD question 7) ------------------------------------------

(defun il-zones () (il-items (il-fetch-json "ZONES")))

(defun il-control-label (item)
  (strcat (il-str (il-j item "code")) "  " (il-str (il-j item "model")) "  [" (il-str (il-j item "category")) "]")
)

(defun c:ILCTRL (/ catalog point items names choice item id cabinet universe start source picked insert)
  (il-begin)
  (setq catalog (il-require-catalog))
  (il-assets-ensure)
  (setq items (il-items (il-j catalog "controllers")))
  (if (null items)
    (princ "\nThe catalog has no controls. Add controller specs in ERPNext, then download the catalog again.")
    (if (and (setq point (getpoint "\nControl location: "))
             (setq choice (il-choose "Control" (setq names (mapcar 'il-control-label items)) 1)))
      (progn
        (setq item (nth (vl-position choice names) items))
        (setq id (il-ask-id "CONTROL" "Control tag" (if (= (il-j item "kind") "decoder") "DEC-" "CTL-")))
        (setq cabinet (il-cabinet-for point))
        (if (il-true-p (il-j item "receives_dmx"))
          (progn
            (initget 6)
            (setq universe (getint "\nDMX universe <1>: "))
            (initget 6)
            (setq start (getint "\nDMX start address (Enter for auto): "))
            (if (and start (> start 512)) (progn (princ "\nAddresses are 1 to 512; using auto.") (setq start nil)))
          )
        )
        (initget "None")
        (setq picked (entsel "\nPick the control that sends its signal, or [None] <None>: "))
        (if (and (listp picked) picked (= (il-kind (car picked)) "CONTROL")) (setq source (il-get "id" (il-xget (car picked)))))
        (setq insert (il-insert (if (= (il-j item "kind") "decoder") "IL-DECODER" "IL-CONTROLLER") point
                                (* 0.4 (il-symbol-scale)) "E-LITE-CTRL-EQPM"
                                (list (cons "TAG" id) (cons "MODEL" (il-j item "code"))
                                      (cons "DMX_ADDR" (if (il-true-p (il-j item "receives_dmx")) (strcat "U" (itoa (if universe universe 1)) "/" (if start (itoa start) "auto")) "")))))
        (il-xset insert (list (cons "kind" "CONTROL") (cons "id" id) (cons "item_code" (il-j item "code"))
                              (cons "cabinet" (if cabinet (il-get "id" (il-xget cabinet)))) (cons "room" (il-room-at point))
                              (cons "universe" (if (il-true-p (il-j item "receives_dmx")) (itoa (if universe universe 1))))
                              (cons "start" (if start (itoa start) "auto")) (cons "control_from" source) (cons "self" (il-handle insert))))
        (princ (strcat "\n" id ": " (il-str (il-j item "code")) (if cabinet (strcat " in " (il-get "id" (il-xget cabinet))) "")
                       ". Group runs it dims with ILZONE; draw its data cable with ILWIRE (Data)."))
      )
    )
  )
  (il-end)
)

(defun c:ILZONE (/ catalog zones name method picked control item ports port ss index ename runs id kept existing action)
  (il-begin)
  (setq catalog (il-require-catalog))
  (setq zones (il-zones))
  (if zones (princ (strcat "\nZones: " (il-join (mapcar '(lambda (z) (strcat (il-str (il-j z "id")) " " (il-str (il-j z "name")))) zones) ", "))))
  (setq name (il-trim (il-ask "Zone name" "Zone")))
  (setq existing (car (vl-remove-if-not '(lambda (z) (= (strcase (il-str (il-j z "name"))) (strcase name))) zones)))
  (if existing
    (progn
      (initget "Add Replace Delete")
      (setq action (getkword (strcat "\n" (il-j existing "id") " " name " has " (itoa (length (il-items (il-j existing "runs"))))
                                     " runs. [Add runs/Replace its runs/Delete the zone] <Add>: ")))
      (if (null action) (setq action "Add"))
    )
  )
  (cond
    ((= action "Delete")
      (il-store-json "ZONES" (il-arr (vl-remove existing zones)))
      (princ (strcat "\n" (il-j existing "id") " " name " deleted.")))
    (T
      (if existing
        (setq method (il-j existing "method") control (il-j existing "control") port (il-j existing "port"))
        (progn
          (setq method (il-choose "How the zone is dimmed" *il-zone-methods* 1))
          (initget "None")
          (setq picked (entsel "\nPick the control whose output dims it, or [None] <None>: "))
          (if (and (listp picked) picked (= (il-kind (car picked)) "CONTROL"))
            (progn
              (setq control (il-get "id" (il-xget (car picked))))
              (setq item (il-cat-control catalog (il-get "item_code" (il-xget (car picked)))))
              (setq ports (if item (il-control-outputs item)))
              (setq port (if ports (il-choose "Output" ports 1) (il-ask "Output port name" "")))
            )
          )
        )
      )
      (princ "\nSelect the runs in the zone.")
      (if (setq ss (ssget '((0 . "LWPOLYLINE"))))
        (progn
          (setq index 0)
          (repeat (sslength ss)
            (setq ename (ssname ss index) index (1+ index))
            (if (and (= (il-kind ename) "RUN") (il-get "id" (il-xget ename))) (setq runs (cons (il-get "id" (il-xget ename)) runs)))
          )
        )
      )
      (setq runs (reverse runs))
      (if (and (= action "Add") existing)
        (foreach id (il-items (il-j existing "runs")) (if (not (member id runs)) (setq runs (cons id runs))))
      )
      (if (null runs)
        (princ "\nNo runs selected; the zone was not saved.")
        (progn
          (setq id (if existing (il-j existing "id") (il-next-zone-id zones)))
          ;; A run belongs to one zone: take the selected runs out of the others.
          (foreach zone zones
            (if (/= (il-j zone "id") id)
              (setq kept (cons (il-jset zone "runs" (il-arr (vl-remove-if '(lambda (run) (member run runs)) (il-items (il-j zone "runs"))))) kept))
            )
          )
          (setq zones (append (reverse kept)
                              (list (il-obj (list (cons "id" id) (cons "name" name) (cons "method" method)
                                                  (cons "control" control) (cons "port" port) (cons "runs" (il-arr runs)))))))
          (il-store-json "ZONES" (il-arr zones))
          (princ (strcat "\n" id " " name ": " (itoa (length runs)) " runs, " (il-str method) (if control (strcat " from " control "/" (il-str port)) "") "."))
        )
      )
    )
  )
  (il-end)
)

(defun c:ILDMX (/ catalog patch point rows scale)
  (il-begin)
  (setq catalog (il-require-catalog))
  (il-assets-ensure)
  (setq patch (il-dmx-patch (il-model) catalog))
  (if (null patch)
    (princ "\nNo DMX receivers in the drawing.")
    (progn
      (princ "\nDMX patch (preview; the System Designer exports the final patch):")
      (foreach row patch
        (princ (strcat "\n  U" (itoa (car row)) "  " (il-str (nth 1 row)) "  " (itoa (nth 2 row)) "-" (itoa (nth 3 row)) (if (nth 4 row) "  (auto)" "")))
      )
      (if (setq point (getpoint "\nTop-left corner for the patch table (Enter to skip): "))
        (progn
          (setq scale (if (il-paper-space-p) 1.0 (il-symbol-scale)))
          (setq rows (cons '("UNIVERSE" "CONTROL" "START" "END" "") (mapcar '(lambda (row) (list (itoa (car row)) (il-str (nth 1 row)) (itoa (nth 2 row)) (itoa (nth 3 row)) (if (nth 4 row) "auto" ""))) patch)))
          (il-table point rows (mapcar '(lambda (w) (* w scale)) '(0.9 1.0 0.6 0.6 0.5)) (* 0.09375 scale))
        )
      )
    )
  )
  (il-end)
)

;; --- Outputs: ILOUT, ILRISER, ILSTRIP (plan 4.1, 4.2, 4.5) ----------------------------------------

;; A text table at POINT: ROWS are lists of strings, the first row the header.
(defun il-table (point rows widths height / y x row-height)
  (setq y (cadr point) row-height (* 2.0 height))
  (foreach row rows
    (setq x (car point))
    (mapcar '(lambda (cell width)
               (entmake (list '(0 . "TEXT") '(8 . "E-ANNO-SCHD") (list 10 (+ x (* 0.25 height)) (- y (* 1.5 height)) 0.0) (cons 40 height) (cons 1 (il-str cell))))
               (setq x (+ x width)))
            row widths)
    (entmake (list '(0 . "LINE") '(8 . "E-ANNO-SCHD") (list 10 (car point) (- y row-height) 0.0) (list 11 x (- y row-height) 0.0)))
    (setq y (- y row-height))
  )
  y
)

(defun c:ILOUT (/ point receipt rows scale cuts)
  (il-begin)
  (il-assets-ensure)
  (setq receipt (il-fetch-json "RECEIPT"))
  (if (null receipt)
    (princ "\nRun ILRECEIPT first: the run schedule and cut list show the server's numbers, not the drawing's.")
    (if (setq point (getpoint "\nTop-left corner of the run schedule: "))
      (progn
        (setq scale (if (il-paper-space-p) 1.0 (il-symbol-scale)))
        (setq rows (list '("RUN" "TYPE" "PART NUMBER" "DRAWN IN" "BUILT IN" "CUT LIST (IN)")))
        (foreach run (il-items (il-j receipt "runs"))
          (setq cuts (il-join (mapcar '(lambda (x) (il-num-text x 2)) (il-items (il-j run "cut_list_in"))) " + "))
          (setq rows (append rows (list (list (il-str (il-j run "id")) (il-str (il-j run "fixture_type")) (il-str (il-j run "part_number"))
                                              (il-num-text (il-j run "drawn_length_in") 2)
                                              (il-num-text (il-j run "server_length_in") 2) cuts))))
        )
        (il-table point rows (mapcar '(lambda (w) (* w scale)) '(0.8 0.6 2.6 0.9 0.9 2.4)) (* 0.09375 scale))
        (princ (strcat "\nRun schedule from import " (il-str (il-j receipt "import")) ". Production builds from the BOM, not this table."))
      )
    )
  )
  (il-end)
)

(defun c:ILRISER (/ path point scale)
  (il-begin)
  (princ "\nThe System Designer exports the riser as DXF. Open it, SAVEAS a DWG, then attach that DWG here.")
  (if (and (setq path (getfiled "Riser drawing (DWG saved from the designer's DXF)" (getvar "DWGPREFIX") "dwg" 0))
           (setq point (getpoint "\nInsertion point: ")))
    (progn
      (setq scale (if (il-paper-space-p) 1.0 (il-symbol-scale)))
      (command "_.-XREF" "_Attach" path "_non" point scale scale 0)
      (princ (strcat "\nRiser attached at " (if (= scale 1.0) "full size." (strcat "the plot scale (" (il-scale-text scale) ")."))))
    )
  )
  (il-end)
)

(defun il-strip-xdata (/ ss index ename)
  (if (setq ss (ssget "_X" (list (list -3 (list *il-app*)))))
    (progn
      (setq index 0)
      (repeat (sslength ss)
        (setq ename (ssname ss index) index (1+ index))
        (entmod (append (vl-remove-if '(lambda (item) (= (car item) -3)) (entget ename)) (list (list -3 (list *il-app*)))))
      )
    )
  )
  (dictremove (namedobjdict) *il-dict*)
)

(defun c:ILSTRIP (/ path)
  (il-begin)
  (setq path (getfiled "Save a copy for the architect as" (strcat (getvar "DWGPREFIX") (vl-filename-base (getvar "DWGNAME")) "-architect") "dwg" 1))
  (cond
    ((null path))
    ((= (strcase path) (strcase (strcat (getvar "DWGPREFIX") (getvar "DWGNAME"))))
      (princ "\nPick a new name: ILSTRIP must not overwrite the drawing you are working in."))
    (T
      (if (findfile path) (command "_.SAVEAS" "" path "_Y") (command "_.SAVEAS" "" path))
      (il-clear-markers)
      (il-strip-xdata)
      (command "_.QSAVE")
      (princ (strcat "\nSaved " path " without ilLumenate data. You are now in the copy; reopen the original to keep working."))
    )
  )
  (il-end)
)

;; --- ILVERSION, ILHELP ------------------------------------------------------------------------

(defun c:ILVERSION ()
  (princ (strcat "\nilLumenate CAD toolkit " *il-version* " on " (il-platform)))
  (foreach pair (il-capabilities) (princ (strcat "\n  " (car pair) ": " (il-str (cdr pair)))))
  (if (il-catalog) (princ (strcat "\n  catalog: " (substr (il-str (il-j (il-catalog) "hash")) 1 8) " generated " (il-str (il-j (il-catalog) "generated_at")))))
  (princ)
)

(defun c:ILHELP ()
  (foreach line
    '("ilLumenate CAD toolkit: draw, check, upload. The portal builds the products and the quote."
      "  ILSETUP     layers, blocks, schedule name, symbol scale, title block"
      "  ILCATALOG   load the CAD catalog downloaded from the portal"
      "  ILSTYLE     choose a run style (saved preset or template and options)"
      "  ILTAPE      draw runs from the feed end, one after another; ILCONVERT turns lines, arcs and polylines into runs"
      "  ILJUMPER    add or remove a jumper at a point; Span marks a gap the jumper crosses"
      "  ILFEED      pick the feed end, feed direction, lead length and feed method"
      "  ILSCALE     calibrate an underlay; ILROOM rooms; ILCAB cabinets; ILPSU supplies"
      "  ILCONNECT   add or remove runs on a PSU; ILWIRE draw a wire path"
      "  ILCTRL      place a controller or decoder; ILZONE add, change or delete a zone; ILDMX patch"
      "  ILOTHER     add, replace or delete another manufacturer's fixture"
      "  ILOVERRIDE  accept a check with a reason, or remove an override"
      "  ILUPDATE    ids (renumbers copies), rooms, tags and links; ILCHECK checks and colours runs"
      "  ILQUOTE     write the .ilq.json package; upload it with Import Drawing on the schedule page"
      "  ILRECEIPT   stamp line keys and part numbers from the import receipt"
      "  ILOUT       run schedule and cut list from the receipt; ILRISER attach the designer's riser"
      "  ILSTRIP     save a copy without ilLumenate data; ILVERSION version and capabilities")
    (princ (strcat "\n" line))
  )
  (princ)
)

(princ (strcat "\nilLumenate CAD toolkit " *il-version* " loaded. Type ILHELP."))
(princ)
