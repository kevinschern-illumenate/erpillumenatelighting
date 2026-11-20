;;; il-controls.lsp -- ilLumenate CAD toolkit: controls in v1 (PRD question 7). Pure: CI runs it.
;;;
;;; Controls are placed in the drawing (ILCTRL) and runs are grouped into zones dimmed by a control
;;; output (ILZONE). The drawing carries what was placed and grouped; the System Designer assigns
;;; outputs, derives control links, exports the DMX patch and checks the system. These are hints:
;;; DMX footprints and address overlaps, a zone's protocol against its control port, data length.
;;;
;;; Model keys: "controls" -- ((id handle item_code cabinet room universe start control_from notes
;;; line_key) ...), start a number or "auto"; "zones" -- ((id name method control port runs) ...).

;; Zone method -> the control protocol a port must send (as the designer's ZONE_CONTROL_PROTOCOL).
(setq *il-zone-protocols*
  '(("DMX512" "DMX512") ("CRMX-wireless" "CRMX-wireless") ("0-10V" "0-10V") ("DALI-2" "DALI-2")
    ("Lutron-QS" "Lutron-QS") ("Lutron-EcoSystem" "Lutron-EcoSystem")
    ("phase-forward" "phase-forward") ("phase-reverse" "phase-reverse"))
)
(setq *il-zone-methods*
  '("DMX512" "CRMX-wireless" "0-10V" "DALI-2" "Lutron-QS" "Lutron-EcoSystem" "phase-forward" "phase-reverse" "none"))

(defun il-cat-control (catalog code / found)
  (foreach item (il-items (il-j catalog "controllers"))
    (if (and (null found) (= (il-j item "code") code)) (setq found item))
  )
  found
)

(defun il-control-port (control-item port-name / found)
  (foreach port (il-items (il-j control-item "ports"))
    (if (and (null found) (= (il-j port "name") port-name)) (setq found port))
  )
  found
)

;; Output ports (not "in") of a catalog control, as names.
(defun il-control-outputs (control-item / names)
  (foreach port (il-items (il-j control-item "ports"))
    (if (/= (il-j port "direction") "in") (setq names (cons (il-j port "name") names)))
  )
  (reverse names)
)

(defun il-model-control (model id / found)
  (foreach control (il-get "controls" model)
    (if (and (null found) (= (il-get "id" control) id)) (setq found control))
  )
  found
)

(defun il-control-footprint (catalog control / item footprint)
  (setq item (il-cat-control catalog (il-get "item_code" control)))
  (setq footprint (if item (il-j item "dmx_footprint")))
  (if (and footprint (> footprint 0)) footprint 1)
)

(defun il-receives-dmx (catalog control / item)
  (setq item (il-cat-control catalog (il-get "item_code" control)))
  (and item (il-true-p (il-j item "receives_dmx")))
)

;; The DMX patch preview: ((universe id start end auto-flag) ...) sorted by universe and start.
;; Fixed addresses keep theirs; "auto" receivers take the next free block, in id order.
(defun il-dmx-patch (model catalog / receivers universes rows used start footprint universe placed)
  (foreach control (il-get "controls" model)
    (if (il-receives-dmx catalog control) (setq receivers (cons control receivers)))
  )
  (setq receivers (vl-sort receivers '(lambda (a b) (< (il-get "id" a) (il-get "id" b)))))
  (foreach control receivers
    (setq universe (if (il-get "universe" control) (il-get "universe" control) 1))
    (if (not (member universe universes)) (setq universes (cons universe universes)))
  )
  (foreach universe (vl-sort universes '<)
    (setq used nil placed nil)
    (foreach control receivers
      (if (and (= (if (il-get "universe" control) (il-get "universe" control) 1) universe)
               (numberp (il-get "start" control)))
        (progn
          (setq start (il-get "start" control) footprint (il-control-footprint catalog control))
          (setq used (cons (list start (+ start footprint -1)) used))
          (setq placed (cons (list universe (il-get "id" control) start (+ start footprint -1) nil) placed))
        )
      )
    )
    (foreach control receivers
      (if (and (= (if (il-get "universe" control) (il-get "universe" control) 1) universe)
               (not (numberp (il-get "start" control))))
        (progn
          (setq footprint (il-control-footprint catalog control) start 1)
          (while (vl-some '(lambda (block) (and (<= start (cadr block)) (>= (+ start footprint -1) (car block)))) used)
            (setq start (1+ (apply 'max (mapcar 'cadr (vl-remove-if-not '(lambda (block) (and (<= start (cadr block)) (>= (+ start footprint -1) (car block)))) used)))))
          )
          (setq used (cons (list start (+ start footprint -1)) used))
          (setq placed (cons (list universe (il-get "id" control) start (+ start footprint -1) T) placed))
        )
      )
    )
    (setq rows (append rows (vl-sort placed '(lambda (a b) (< (caddr a) (caddr b))))))
  )
  rows
)

;; Control issues, appended by il-check: ((code ref severity text) ...).
(defun il-check-controls (model catalog / issues ids item zoned control port protocol wanted patch wire limit source)
  (foreach control (il-get "controls" model)
    (setq ids (cons (il-get "id" control) ids))
    (setq item (if catalog (il-cat-control catalog (il-get "item_code" control))))
    (cond
      ((and catalog (null item))
        (il-add "CONTROL_UNKNOWN" (il-get "id" control) "error"
          (strcat (il-str (il-get "item_code" control)) " is not a control in the current catalog")))
      ((and (il-receives-dmx catalog control) (null (il-get "control_from" control))
            (not (vl-some '(lambda (w) (member (il-get "id" control) (list (il-get "from" w) (il-get "to" w)))) (il-get "wires" model))))
        (il-add "CONTROL_NO_SIGNAL" (il-get "id" control) "warning" "Decoder has no DMX source: set its controller or draw a data wire (ILWIRE)"))
    )
    (if (and (setq source (il-get "control_from" control)) (null (il-model-control model source)))
      (il-add "CONTROL_UNKNOWN_SOURCE" (il-get "id" control) "error" (strcat "Signal source " source " is not a control"))
    )
  )
  ;; DMX: addresses inside 1-512, no overlaps, no full universes.
  (if catalog
    (progn
      (setq patch (il-dmx-patch model catalog))
      (foreach row patch
        (if (> (nth 3 row) 512)
          (il-add "DMX_UNIVERSE_FULL" (nth 1 row) "error"
            (strcat "Needs channels " (itoa (nth 2 row)) "-" (itoa (nth 3 row)) " in universe " (itoa (car row)) " (512 max)")))
        (foreach other patch
          (if (and (= (car row) (car other)) (< (nth 1 row) (nth 1 other))
                   (<= (nth 2 row) (nth 3 other)) (>= (nth 3 row) (nth 2 other)))
            (il-add "DMX_ADDRESS_OVERLAP" (nth 1 row) "error"
              (strcat (nth 1 row) " and " (nth 1 other) " share channels in universe " (itoa (car row)))))
        )
      )
    )
  )
  ;; Zones: a control output in the zone's protocol, runs in one zone only.
  (foreach zone (il-get "zones" model)
    (if (null (il-get "runs" zone)) (il-add "ZONE_EMPTY" (il-get "id" zone) "warning" "Zone has no runs"))
    (foreach run (il-get "runs" zone)
      (if (member run zoned)
        (il-add "RUN_IN_TWO_ZONES" run "error" (strcat run " is in more than one zone"))
        (setq zoned (cons run zoned))
      )
    )
    (setq wanted (cadr (assoc (il-get "method" zone) *il-zone-protocols*)))
    (cond
      ((null (il-get "control" zone))
        (if (and wanted (not (member (il-get "method" zone) '("0-10V" "DALI-2" "phase-forward" "phase-reverse"))))
          (il-add "ZONE_NO_CONTROL" (il-get "id" zone) "warning" (strcat (il-get "method" zone) " zone has no control output"))))
      ((null (setq control (il-model-control model (il-get "control" zone))))
        (il-add "ZONE_UNKNOWN_CONTROL" (il-get "id" zone) "error" (strcat (il-get "control" zone) " is not a control in the drawing")))
      ((and catalog (setq item (il-cat-control catalog (il-get "item_code" control))))
        (setq port (il-control-port item (il-get "port" zone)))
        (setq protocol (if port (il-j port "protocol")))
        (cond
          ((null port)
            (il-add "PROTOCOL_MISMATCH" (il-get "id" zone) "error"
              (strcat (il-get "control" zone) " has no output " (il-str (il-get "port" zone)))))
          ((and wanted (/= protocol wanted))
            (il-add "PROTOCOL_MISMATCH" (il-get "id" zone) "error"
              (strcat (il-get "method" zone) " zone on a " (il-str protocol) " output of " (il-get "control" zone))))
        )
      )
    )
  )
  ;; Data length from controls that limit it (pixel data, SPI).
  (foreach wire (il-get "wires" model)
    (if (and catalog (= (il-get "kind" wire) "data") (setq control (il-model-control model (il-get "from" wire)))
             (setq item (il-cat-control catalog (il-get "item_code" control)))
             (setq limit (il-j item "max_data_length_ft"))
             (> (/ (il-get "length_in" wire) 12.0) limit))
      (il-add "DATA_TOO_LONG" (il-get "id" wire) "warning"
        (strcat (il-num->str (/ (il-get "length_in" wire) 12.0) 1) " ft of data from " (il-get "id" control)
                "; it allows " (il-num->str limit 1) " ft"))
    )
  )
  (reverse issues)
)

;; The package's "controls" and "zones" sections.
(defun il-package-controls (model / dmx)
  (il-arr
    (mapcar
      '(lambda (control / pairs)
         (setq pairs (list (cons "id" (il-get "id" control)) (cons "handle" (il-get "handle" control))
                           (cons "item_code" (il-get "item_code" control))))
         (setq pairs (il-opt "cabinet" (il-get "cabinet" control) pairs))
         (setq pairs (il-opt "room" (il-get "room" control) pairs))
         (if (il-get "universe" control)
           (setq pairs (append pairs (list (cons "dmx" (il-obj (list (cons "universe" (il-get "universe" control))
                                                                    (cons "start_address" (if (numberp (il-get "start" control)) (il-get "start" control) "auto")))))))))
         (setq pairs (il-opt "control_from" (il-get "control_from" control) pairs))
         (setq pairs (il-opt "notes" (il-get "notes" control) pairs))
         (il-obj (append pairs (list (cons "erp" (il-obj (il-opt "line_key" (il-get "line_key" control) nil))))))
       )
      (il-get "controls" model)
    )
  )
)

(defun il-package-zones (model)
  (il-arr
    (mapcar
      '(lambda (zone / pairs)
         (setq pairs (list (cons "id" (il-get "id" zone)) (cons "name" (il-get "name" zone)) (cons "method" (il-get "method" zone))))
         (if (il-get "control" zone)
           (setq pairs (append pairs (list (cons "control" (il-obj (list (cons "id" (il-get "control" zone)) (cons "port" (il-get "port" zone)))))))))
         (il-obj (append pairs (list (cons "runs" (il-arr (il-get "runs" zone))))))
       )
      (il-get "zones" model)
    )
  )
)
