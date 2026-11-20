;;; il-spike.lsp -- Phase 0.2 capability spike for the ilLumenate CAD toolkit.
;;;
;;; Run on each AutoCAD a dealer may use (full Windows, LT 2024/2025, Mac): APPLOAD this file in an
;;; empty drawing, then type ILSPIKE. It tries each capability the toolkit relies on (or avoids) and
;;; writes ilLumenate-spike-<product>.txt next to the drawing. Send the files to engineering; they fill
;;; the capability matrix in docs/CAD_TOOLKIT_IMPLEMENTATION.md. Nothing here changes the drawing
;;; after the run: every test entity is erased.

(defun il-spike-try (name function / result)
  (setq result (vl-catch-all-apply function nil))
  (cons name (if (vl-catch-all-error-p result) (strcat "FAIL " (vl-catch-all-error-message result)) (if result "OK" "NO")))
)

(defun il-spike-line (/ ename)
  (entmake '((0 . "LINE") (10 0.0 0.0 0.0) (11 10.0 0.0 0.0)))
  (setq ename (entlast))
  ename
)

(defun c:ILSPIKE (/ results ename path file marker next)
  (setq marker (entlast))
  (setq results
    (list
      (cons "product" (getvar "PRODUCT"))
      (cons "acadver" (getvar "ACADVER"))
      (cons "platform" (getvar "PLATFORM"))
      (il-spike-try "entmake LINE" '(lambda () (setq ename (il-spike-line))))
      (il-spike-try "regapp + XData write" '(lambda ()
        (regapp "ILLUMENATE")
        (entmod (append (entget ename) (list (list -3 (list "ILLUMENATE" (cons 1000 "kind") (cons 1000 "SPIKE"))))))))
      (il-spike-try "XData read" '(lambda () (assoc -3 (entget ename '("ILLUMENATE")))))
      (il-spike-try "ssget _X by XData" '(lambda () (ssget "_X" '((-3 ("ILLUMENATE"))))))
      (il-spike-try "entmake LWPOLYLINE with bulge" '(lambda ()
        (entmake '((0 . "LWPOLYLINE") (100 . "AcDbEntity") (100 . "AcDbPolyline") (90 . 2) (70 . 0) (10 0.0 0.0) (42 . 0.5) (10 10.0 0.0)))))
      (il-spike-try "entmake BLOCK/ATTDEF/ENDBLK" '(lambda ()
        (entmake '((0 . "BLOCK") (2 . "IL-SPIKE") (70 . 2) (10 0.0 0.0 0.0)))
        (entmake '((0 . "ATTDEF") (8 . "0") (10 0.0 0.0 0.0) (40 . 0.1) (1 . "") (3 . "TAG") (2 . "TAG") (70 . 0)))
        (entmake '((0 . "ENDBLK")))))
      (il-spike-try "namedobjdict XRECORD" '(lambda ()
        (dictadd (namedobjdict) "IL-SPIKE" (entmakex '((0 . "XRECORD") (100 . "AcDbXrecord") (1 . "spike"))))))
      (il-spike-try "dictremove" '(lambda () (dictremove (namedobjdict) "IL-SPIKE")))
      (il-spike-try "command PLINE via script" '(lambda () (command "_.PLINE" "0,0" "5,5" "") T))
      (il-spike-try "getfiled available" '(lambda () (= (type getfiled) 'SUBR)))
      (il-spike-try "vl-string-search" '(lambda () (vl-string-search "b" "abc")))
      (il-spike-try "vl-sort" '(lambda () (vl-sort '(3 1 2) '<)))
      (il-spike-try "vl-catch-all-apply" '(lambda () T))
      (il-spike-try "logand/lsh/boole (SHA-256)" '(lambda () (and (= (logand 12 10) 8) (= (lsh 1 4) 16) (= (boole 6 12 10) 6))))
      (il-spike-try "vlax (ActiveX, not used by the core)" '(lambda () (vl-load-com) (vlax-get-acad-object)))
      (il-spike-try "vlr reactors (not used)" '(lambda () (= (type vlr-object-reactor) 'SUBR)))
      (il-spike-try "DCL load_dialog (not used)" '(lambda () (= (type load_dialog) 'SUBR)))
      (il-spike-try "setenv/getenv" '(lambda () (setenv "ILLUMENATE_SPIKE" "1") (= (getenv "ILLUMENATE_SPIKE") "1")))
    )
  )
  (setq path (strcat (getvar "DWGPREFIX") "ilLumenate-spike-" (vl-string-translate " /\\:" "____" (getvar "PRODUCT")) ".txt"))
  (setq results (append results (list (il-spike-try "file write" '(lambda () (setq file (open path "w")) (write-line "ilLumenate spike" file) (close file) T)))))
  (if (setq file (open path "w"))
    (progn
      (foreach pair results (write-line (strcat (car pair) ": " (vl-princ-to-string (cdr pair))) file))
      (close file)
    )
  )
  (foreach pair results (princ (strcat "\n" (car pair) ": " (vl-princ-to-string (cdr pair)))))
;; Erase only what the spike made: everything after the drawing's last entity at the start.
  (setq next (if marker (entnext marker) (entnext)))
  (while next (entdel next) (setq next (entnext next)))
  (princ (strcat "\nWrote " path))
  (princ)
)
