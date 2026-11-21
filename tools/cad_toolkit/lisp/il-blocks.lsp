;;; il-blocks.lsp -- ilLumenate CAD toolkit: layers, linetypes and blocks from il-assets.lsp (3.3, 3.4).
;;;
;;; The asset data is generated from the riser's layer standard, symbols and title blocks, so the plan
;;; and the riser read the same. Everything is made with entmake: no DWG library, LT and Mac safe.

(defun il-ensure-linetype (row / name pattern total items)
  (setq name (car row) pattern (caddr row))
  (if (and (not (tblsearch "LTYPE" name)) (/= (strcase name) "CONTINUOUS"))
    (progn
      (setq total 0.0)
      (foreach dash pattern (setq total (+ total (abs dash))))
      (setq items nil)
      (foreach dash pattern (setq items (append items (list (cons 49 dash) (cons 74 0)))))
      (entmake
        (append
          (list '(0 . "LTYPE") '(100 . "AcDbSymbolTableRecord") '(100 . "AcDbLinetypeTableRecord")
                (cons 2 name) '(70 . 0) (cons 3 (cadr row)) '(72 . 65) (cons 73 (length pattern)) (cons 40 total))
          items
        )
      )
    )
  )
)

(defun il-ensure-layer (row / name)
  (setq name (nth 0 row))
  (if (not (tblsearch "LAYER" name))
    (progn
      (regapp "AcAecLayerStandard")
      (entmake
        (list '(0 . "LAYER") '(100 . "AcDbSymbolTableRecord") '(100 . "AcDbLayerTableRecord")
              (cons 2 name) '(70 . 0) (cons 62 (nth 1 row)) (cons 6 (nth 2 row))
              (cons 370 (fix (+ 0.5 (* 100 (nth 3 row))))) (cons 290 (if (nth 4 row) 1 0))
              (list -3 (list "AcAecLayerStandard" (cons 1000 "") (cons 1000 (nth 5 row)))))
      )
    )
  )
)

(defun il-make-item (item / kind points data)
  (setq kind (car item))
  (cond
    ((= kind "LINE")
      (entmake (list '(0 . "LINE") (cons 8 (nth 5 item)) (list 10 (nth 1 item) (nth 2 item) 0.0) (list 11 (nth 3 item) (nth 4 item) 0.0))))
    ((= kind "PLINE")
      (setq points (nth 1 item) data nil)
      (while points
        (setq data (append data (list (list 10 (car points) (cadr points)))) points (cddr points))
      )
      (entmake (append (list '(0 . "LWPOLYLINE") '(100 . "AcDbEntity") (cons 8 (nth 3 item)) '(100 . "AcDbPolyline")
                             (cons 90 (length data)) (cons 70 (if (nth 2 item) 1 0)))
                       data)))
    ((= kind "CIRCLE")
      (entmake (list '(0 . "CIRCLE") (cons 8 (nth 4 item)) (list 10 (nth 1 item) (nth 2 item) 0.0) (cons 40 (nth 3 item)))))
    ((= kind "ARC")
      (entmake (list '(0 . "ARC") (cons 8 (nth 6 item)) (list 10 (nth 1 item) (nth 2 item) 0.0) (cons 40 (nth 3 item))
                     (cons 50 (* pi (/ (nth 4 item) 180.0))) (cons 51 (* pi (/ (nth 5 item) 180.0))))))
    ((= kind "TEXT")
      (entmake (list '(0 . "TEXT") (cons 8 (nth 6 item)) (list 10 (nth 1 item) (nth 2 item) 0.0) (cons 40 (nth 3 item))
                     (cons 1 (nth 4 item)))))
    ((= kind "ATTDEF")
      (entmake (append (list '(0 . "ATTDEF") (cons 8 (nth 7 item)) (list 10 (nth 2 item) (nth 3 item) 0.0) (cons 40 (nth 4 item))
                             (cons 1 (nth 5 item)) (cons 3 (nth 1 item)) (cons 2 (nth 1 item)) (cons 70 (if (nth 6 item) 0 1)))
                       (il-align-groups item (list (nth 2 item) (nth 3 item) 0.0)))))
  )
)

(defun il-ensure-block (block / name has-attributes)
  (setq name (car block))
  (if (not (tblsearch "BLOCK" name))
    (progn
      (foreach item (cddr block) (if (= (car item) "ATTDEF") (setq has-attributes T)))
      (entmake (list '(0 . "BLOCK") (cons 2 name) (cons 70 (if has-attributes 2 0)) '(10 0.0 0.0 0.0) (cons 4 (cadr block))))
      (foreach item (cddr block) (il-make-item item))
      (entmake '((0 . "ENDBLK")))
    )
  )
  name
)

;; Layers, linetypes and every block. Safe to run again: existing records are kept.
(defun il-assets-ensure ()
  (foreach row *il-asset-linetypes* (il-ensure-linetype row))
  (foreach row *il-asset-layers* (il-ensure-layer row))
  (foreach block *il-asset-blocks* (il-ensure-block block))
  T
)

(defun il-block-data (name / found)
  (foreach block *il-asset-blocks* (if (= (car block) name) (setq found block)))
  found
)

;; Insert block NAME at POINT with ATTRIBUTES ((tag . value) ...) on LAYER; returns the INSERT. When
;; *il-layout* is set (tags of an entity) it goes on that layout, else in the current space.
(defun il-insert (name point scale layer attributes / block insert at)
  (il-ensure-block (il-block-data name))
  (setq block (il-block-data name))
  (entmake (append (list '(0 . "INSERT") (cons 8 layer) (cons 2 name) (cons 10 point) (cons 41 scale) (cons 42 scale) (cons 43 scale)
                         (cons 66 (if (vl-some '(lambda (item) (= (car item) "ATTDEF")) (cddr block)) 1 0)))
                   (if *il-layout* (list (cons 410 *il-layout*)))))
  (foreach item (cddr block)
    (if (= (car item) "ATTDEF")
      (progn
        (setq at (il-attdef-point point scale 0.0 item))
        (entmake (append (list '(0 . "ATTRIB") (cons 8 (nth 7 item)) (cons 10 at) (cons 40 (* scale (nth 4 item)))
                               (cons 1 (il-str (il-get (nth 1 item) attributes))) (cons 2 (nth 1 item))
                               (cons 70 (if (nth 6 item) 0 1)))
                         (il-align-groups item at)))
      )
    )
  )
  (if (vl-some '(lambda (item) (= (car item) "ATTDEF")) (cddr block)) (entmake '((0 . "SEQEND"))))
  (entlast)
)

;; The ATTDEF item for TAG in BLOCK data.
(defun il-attdef-item (block tag / found)
  (foreach item (cddr block)
    (if (and (= (car item) "ATTDEF") (= (strcase (nth 1 item)) (strcase tag))) (setq found item))
  )
  found
)

;; Tags placed before 0.4.2 have left-aligned text where the block now centres it: re-place those
;; attributes centred (once; a centred attribute is left where it is). Returns how many moved.
(defun il-recenter-tags (/ ss index ename data block base scale rotation next attribute item point count)
  (setq count 0)
  (if (setq ss (ssget "_X" '((0 . "INSERT") (2 . "IL-*"))))
    (progn
      (setq index 0)
      (repeat (sslength ss)
        (setq ename (ssname ss index) index (1+ index) data (entget ename) block (il-block-data (cdr (assoc 2 data))))
        (if block
          (progn
            (setq base (cdr (assoc 10 data)) scale (cdr (assoc 41 data)) next (entnext ename)
                  rotation (if (numberp (cdr (assoc 50 data))) (cdr (assoc 50 data)) 0.0))
            (while (and next (= (cdr (assoc 0 (setq attribute (entget next)))) "ATTRIB"))
              (setq item (il-attdef-item block (cdr (assoc 2 attribute))))
              (if (and item (= (nth 8 item) "center") (not (equal (cdr (assoc 72 attribute)) 1)))
                (progn
                  (setq point (il-attdef-point base scale rotation item))
                  (foreach group (cons (cons 10 point) (il-align-groups item point))
                    (setq attribute (il-set-group (car group) (cdr group) attribute))
                  )
                  (entmod attribute)
                  (setq count (1+ count))
                )
              )
              (setq next (entnext next))
            )
            (entupd ename)
          )
        )
      )
    )
  )
  count
)

;; Set attribute TAG of the INSERT ENAME to VALUE.
(defun il-set-attribute (ename tag value / next data)
  (setq next (entnext ename))
  (while (and next (= (cdr (assoc 0 (setq data (entget next)))) "ATTRIB"))
    (if (= (strcase (cdr (assoc 2 data))) (strcase tag))
      (progn (entmod (subst (cons 1 (il-str value)) (assoc 1 data) data)) (entupd ename))
    )
    (setq next (entnext next))
  )
)
