;;; il-core.lsp -- ilLumenate CAD toolkit: command wrapper, XData and drawing storage (plan 3.1).
;;;
;;; Every command runs inside il-begin / il-end: one undo step, system variables restored, and an
;;; *error* handler that puts both back if the user cancels. Entities carry XData under the app
;;; "ILLUMENATE" as key/value strings with a schema version; long data (styles, settings, other
;;; lines, overrides) lives in XRECORDs of the "ILLUMENATE" dictionary in the named object dictionary.
;;; Only entget/entmod/entmake and dictionary functions: works on full AutoCAD, LT 2024+ and Mac.

(setq *il-app* "ILLUMENATE" *il-dict* "ILLUMENATE" *il-xdata-schema* 1)
(setq *il-sysvars* '("CMDECHO" "OSMODE" "CLAYER" "ATTREQ" "ATTDIA" "DIMZIN"))

;; --- Command wrapper ----------------------------------------------------------------------------

(defun il-begin (/ saved)
  (setq *il-saved-vars* (mapcar '(lambda (name) (cons name (getvar name))) *il-sysvars*))
  (setq *il-old-error* *error*)
  (setq *error* il-error)
  (setvar "CMDECHO" 0)
  (setvar "ATTREQ" 0)
  (setvar "DIMZIN" 8)
  (command "_.UNDO" "_BEGIN")
  T
)

(defun il-restore ()
  (foreach pair *il-saved-vars*
    (if (cdr pair) (vl-catch-all-apply 'setvar (list (car pair) (cdr pair))))
  )
)

(defun il-end ()
  (command "_.UNDO" "_END")
  (il-restore)
  (setq *error* *il-old-error*)
  (princ)
)

(defun il-error (message)
  (while (> (getvar "CMDACTIVE") 0) (command))
  (command "_.UNDO" "_END")
  (il-restore)
  (setq *error* *il-old-error*)
  (if (not (member message '("Function cancelled" "quit / exit abort" "console break")))
    (princ (strcat "\nilLumenate: " message))
  )
  (princ)
)

;; Capability report for the Phase 0 spike and ILVERSION: what this AutoCAD offers.
(defun il-capabilities ()
  (list
    (cons "product" (getvar "PRODUCT"))
    (cons "version" (getvar "ACADVER"))
    (cons "platform" (getvar "PLATFORM"))
    (cons "activex" (if (= (type vlax-get-acad-object) 'SUBR) "yes" "no"))
    (cons "reactors" (if (= (type vlr-object-reactor) 'SUBR) "yes" "no"))
    (cons "dcl" (if (= (type load_dialog) 'SUBR) "yes" "no"))
  )
)

(defun il-platform ()
  (strcat (getvar "PRODUCT") " " (substr (getvar "ACADVER") 1 4))
)

;; --- XData ------------------------------------------------------------------------------------

;; The ILLUMENATE XData of ENAME as ((key . value) ...), migrated to the current schema.
(defun il-xget (ename / data items result key)
  (setq data (cdr (assoc -3 (entget ename (list *il-app*)))))
  (setq items (cdr (assoc *il-app* data)))
  (while items
    (if (= (car (car items)) 1000)
      (progn
        (setq key (cdr (car items)) items (cdr items))
        (setq result (cons (cons key (if items (cdr (car items)) "")) result))
      )
    )
    (setq items (cdr items))
  )
  (il-xmigrate (reverse result))
)

;; Schema migrations: each step lifts XData written by an older toolkit. Version 1 is the first.
(defun il-xmigrate (pairs / version)
  (setq version (atoi (il-str (il-get "sv" pairs))))
  (cond
    ((null pairs) nil)
    ((< version 1) (il-put "sv" "1" pairs))
    (T pairs)
  )
)

;; Replace ENAME's ILLUMENATE XData with PAIRS ((key . value) ...); values become text <= 250 chars.
(defun il-xset (ename pairs / data entity)
  (regapp *il-app*)
  (setq pairs (il-put "sv" (itoa *il-xdata-schema*) pairs))
  (foreach pair pairs
    (if (and (cdr pair) (/= (il-str (cdr pair)) ""))
      (setq data (append data (list (cons 1000 (car pair)) (cons 1000 (substr (il-str (cdr pair)) 1 250)))))
    )
  )
  (setq entity (vl-remove-if '(lambda (item) (= (car item) -3)) (entget ename)))
  (entmod (append entity (list (list -3 (cons *il-app* data)))))
  (entupd ename)
)

(defun il-xupdate (ename changes / pairs)
  (setq pairs (il-xget ename))
  (foreach change changes (setq pairs (il-put (car change) (cdr change) pairs)))
  (il-xset ename pairs)
)

(defun il-kind (ename) (il-get "kind" (il-xget ename)))

;; Every entity with ILLUMENATE XData of KIND ("RUN", "ROOM", "CABINET", "PSU", "WIRE").
(defun il-entities (kind / ss index result ename)
  (if (setq ss (ssget "_X" (list (list -3 (list *il-app*)))))
    (progn
      (setq index 0)
      (repeat (sslength ss)
        (setq ename (ssname ss index) index (1+ index))
        (if (= (il-kind ename) kind) (setq result (cons ename result)))
      )
    )
  )
  (reverse result)
)

(defun il-handle (ename) (cdr (assoc 5 (entget ename))))

(defun il-find-id (kind id / found)
  (foreach ename (il-entities kind)
    (if (= (il-get "id" (il-xget ename)) id) (setq found ename))
  )
  found
)

;; The next free tag: (il-next-id "RUN" "L1-") returns "L1-03".
(defun il-next-id (kind prefix / used number)
  (foreach ename (il-entities kind)
    (setq used (cons (il-get "id" (il-xget ename)) used))
  )
  (setq number 1)
  (while (member (strcat prefix (il-pad2 number)) used) (setq number (1+ number)))
  (strcat prefix (il-pad2 number))
)

;; --- Drawing storage (named object dictionary) ------------------------------------------------

(defun il-dict (/ found)
  (if (setq found (dictsearch (namedobjdict) *il-dict*))
    (cdr (assoc -1 found))
    (dictadd (namedobjdict) *il-dict* (entmakex '((0 . "DICTIONARY") (100 . "AcDbDictionary"))))
  )
)

;; Store TEXT under KEY, in 250-character chunks.
(defun il-store (key text / dict chunks index)
  (setq dict (il-dict) index 1)
  (while (<= index (strlen text))
    (setq chunks (cons (cons 1 (substr text index 250)) chunks) index (+ index 250))
  )
  (if (dictsearch dict key) (entdel (cdr (assoc -1 (dictsearch dict key)))))
  (dictremove dict key)
  (dictadd dict key
    (entmakex (append '((0 . "XRECORD") (100 . "AcDbXrecord")) (reverse chunks) (if (null chunks) '((1 . "")))))
  )
  text
)

(defun il-fetch (key / record)
  (if (setq record (dictsearch (il-dict) key))
    (apply 'strcat (mapcar 'cdr (vl-remove-if-not '(lambda (item) (= (car item) 1)) record)))
  )
)

;; JSON values in the dictionary.
(defun il-store-json (key value) (il-store key (il-json-text value)) value)
(defun il-fetch-json (key / text)
  (if (and (setq text (il-fetch key)) (/= text "")) (il-json-parse text))
)

;; Drawing settings: an object of schedule, project, catalog path and hash, revision, scale flag.
(defun il-settings () (if (il-fetch-json "SETTINGS") (il-fetch-json "SETTINGS") (il-obj nil)))
(defun il-setting (key) (il-j (il-settings) key))
(defun il-set-setting (key value) (il-store-json "SETTINGS" (il-jset (il-settings) key value)))

;; --- Prompts ----------------------------------------------------------------------------------

;; Pick one of ITEMS (strings) by number; DEFAULT-INDEX is 1-based. Returns the item or nil.
(defun il-choose (title items default-index / index answer)
  (princ (strcat "\n" title ":"))
  (setq index 1)
  (foreach item items
    (princ (strcat "\n  " (itoa index) ". " item))
    (setq index (1+ index))
  )
  (initget 4)
  (setq answer (getint (strcat "\nNumber" (if default-index (strcat " <" (itoa default-index) ">") "") ": ")))
  (if (null answer) (setq answer default-index))
  (if (and answer (> answer 0) (<= answer (length items))) (nth (1- answer) items))
)

(defun il-ask (message default / answer)
  (setq answer (getstring T (strcat "\n" message (if (and default (/= default "")) (strcat " <" default ">") "") ": ")))
  (if (= answer "") default answer)
)

(defun il-today (/ date)
  (setq date (rtos (getvar "CDATE") 2 0))
  (strcat (substr date 1 4) "-" (substr date 5 2) "-" (substr date 7 2))
)

;; --- Geometry ---------------------------------------------------------------------------------

;; ((x y bulge) ...) of an LWPOLYLINE, and whether it is closed.
(defun il-lw-vertices (ename / data result point)
  (setq data (entget ename))
  (foreach item data
    (cond
      ((= (car item) 10) (setq point (list (cadr item) (caddr item) 0.0) result (cons point result)))
      ((and (= (car item) 42) result)
        (setq result (cons (list (car (car result)) (cadr (car result)) (cdr item)) (cdr result))))
    )
  )
  (reverse result)
)

(defun il-lw-closed (ename) (= 1 (logand 1 (cdr (assoc 70 (entget ename))))))

(defun il-point-in-polygon (point vertices / inside a b count index)
  (setq count (length vertices) index 0)
  (while (< index count)
    (setq a (nth index vertices) b (nth (rem (1+ index) count) vertices))
    (if (and (/= (> (cadr a) (cadr point)) (> (cadr b) (cadr point)))
             (< (car point) (+ (car a) (/ (* (- (car b) (car a)) (- (cadr point) (cadr a))) (- (cadr b) (cadr a))))))
      (setq inside (not inside))
    )
    (setq index (1+ index))
  )
  inside
)

(defun il-midpoint (vertices / a b)
  (setq a (car vertices) b (last vertices))
  (list (/ (+ (car a) (car b)) 2.0) (/ (+ (cadr a) (cadr b)) 2.0) 0.0)
)

(defun il-centroid (vertices / x y)
  (setq x 0.0 y 0.0)
  (foreach v vertices (setq x (+ x (car v)) y (+ y (cadr v))))
  (list (/ x (length vertices)) (/ y (length vertices)) 0.0)
)

;; Plan symbols are drawn in paper inches; insert them at the drawing's annotation scale.
(defun il-symbol-scale (/ scale)
  (setq scale (il-number (il-setting "symbol_scale")))
  (if (and scale (> scale 0)) scale (max 1.0 (getvar "DIMSCALE")))
)
