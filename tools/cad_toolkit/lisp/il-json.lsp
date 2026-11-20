;;; il-json.lsp -- ilLumenate CAD toolkit: a small JSON reader and writer (no network, no ActiveX).
;;;
;;; Values: an object is (IL-OBJ (key . value) ...), an array (IL-ARR item ...), true IL-TRUE,
;;; false IL-FALSE, null nil; strings and numbers are themselves. The reader takes a file (line by
;;; line, so a large catalog never becomes one huge string) or a string. Pure: CI runs it.

;; --- Constructors and accessors ----------------------------------------------------------------

(defun il-obj (pairs) (cons 'IL-OBJ pairs))
(defun il-arr (items) (cons 'IL-ARR items))
(defun il-obj-p (value) (and (listp value) value (eq (car value) 'IL-OBJ)))
(defun il-arr-p (value) (and (listp value) value (eq (car value) 'IL-ARR)))
(defun il-true-p (value) (eq value 'IL-TRUE))
(defun il-bool (flag) (if flag 'IL-TRUE 'IL-FALSE))

;; The value at KEY of an object (nil when absent or null).
(defun il-j (obj key)
  (if (il-obj-p obj) (il-get key (cdr obj)))
)

;; The value at a key path: (il-jp catalog '("settings" "stale_days")).
(defun il-jp (value path)
  (foreach key path (setq value (il-j value key)))
  value
)

;; The items of an array (nil for anything else).
(defun il-items (value)
  (if (il-arr-p value) (cdr value))
)

(defun il-keys (obj)
  (if (il-obj-p obj) (mapcar 'car (cdr obj)))
)

(defun il-jset (obj key value)
  (il-obj (il-put key value (cdr obj)))
)

;; --- Reader -----------------------------------------------------------------------------------
;; State: *il-jr-text* is the current chunk, *il-jr-pos* the 1-based position in it, *il-jr-file*
;; the open file (or nil when reading a string).

(defun il-jr-more ()
  (if (and *il-jr-file* (> *il-jr-pos* (strlen *il-jr-text*)))
    (progn
      (setq *il-jr-text* (read-line *il-jr-file*) *il-jr-pos* 1)
      (if *il-jr-text* (setq *il-jr-text* (strcat *il-jr-text* "\n")) (setq *il-jr-text* "" *il-jr-file* nil))
    )
  )
  (<= *il-jr-pos* (strlen *il-jr-text*))
)

(defun il-jr-peek ()
  (if (il-jr-more) (substr *il-jr-text* *il-jr-pos* 1))
)

(defun il-jr-next (/ char)
  (if (setq char (il-jr-peek)) (setq *il-jr-pos* (1+ *il-jr-pos*)))
  char
)

(defun il-jr-space (/ char)
  (while (and (setq char (il-jr-peek)) (member char '(" " "\t" "\n" "\r")))
    (setq *il-jr-pos* (1+ *il-jr-pos*))
  )
)

(defun il-jr-fail (message)
  (setq *il-jr-error* message)
  (exit)
)

(defun il-jr-expect (word / index)
  (setq index 1)
  (while (<= index (strlen word))
    (if (/= (il-jr-next) (substr word index 1)) (il-jr-fail (strcat "JSON: expected " word)))
    (setq index (1+ index))
  )
)

(defun il-jr-hex (text / value index char code)
  (setq value 0 index 1)
  (while (<= index (strlen text))
    (setq char (strcase (substr text index 1)) code (ascii char))
    (setq value (+ (* value 16) (if (>= code 65) (- code 55) (- code 48))))
    (setq index (1+ index))
  )
  value
)

(defun il-jr-string (/ parts char escape code done)
  (il-jr-next) ; opening quote
  (while (not done)
    (setq char (il-jr-next))
    (cond
      ((null char) (il-jr-fail "JSON: unterminated string"))
      ((= char "\"") (setq done T))
      ((= char "\\")
        (setq escape (il-jr-next))
        (setq parts
          (cons
            (cond
              ((= escape "n") "\n")
              ((= escape "t") "\t")
              ((= escape "r") "\r")
              ((= escape "b") "")
              ((= escape "f") "")
              ((= escape "u")
                (setq code (il-jr-hex (strcat (il-jr-next) (il-jr-next) (il-jr-next) (il-jr-next))))
                (if (and (> code 31) (< code 127)) (chr code) "?")
              )
              (T escape)
            )
            parts
          )
        )
      )
      (T (setq parts (cons char parts)))
    )
  )
  (apply 'strcat (reverse parts))
)

(defun il-jr-number (/ text char real)
  (setq text "")
  (while (and (setq char (il-jr-peek)) (vl-string-search char "+-0123456789.eE"))
    (if (vl-string-search char ".eE") (setq real T))
    (setq text (strcat text char) *il-jr-pos* (1+ *il-jr-pos*))
  )
  (if (or real (> (strlen text) 9)) (atof text) (atoi text))
)

(defun il-jr-value (/ char items pairs key)
  (il-jr-space)
  (setq char (il-jr-peek))
  (cond
    ((null char) (il-jr-fail "JSON: unexpected end"))
    ((= char "{")
      (il-jr-next)
      (il-jr-space)
      (if (= (il-jr-peek) "}")
        (il-jr-next)
        (progn
          (setq char ",")
          (while (= char ",")
            (il-jr-space)
            (setq key (il-jr-string))
            (il-jr-space)
            (if (/= (il-jr-next) ":") (il-jr-fail "JSON: expected :"))
            (setq pairs (cons (cons key (il-jr-value)) pairs))
            (il-jr-space)
            (setq char (il-jr-next))
          )
          (if (/= char "}") (il-jr-fail "JSON: expected }"))
        )
      )
      (il-obj (reverse pairs))
    )
    ((= char "[")
      (il-jr-next)
      (il-jr-space)
      (if (= (il-jr-peek) "]")
        (il-jr-next)
        (progn
          (setq char ",")
          (while (= char ",")
            (setq items (cons (il-jr-value) items))
            (il-jr-space)
            (setq char (il-jr-next))
          )
          (if (/= char "]") (il-jr-fail "JSON: expected ]"))
        )
      )
      (il-arr (reverse items))
    )
    ((= char "\"") (il-jr-string))
    ((= char "t") (il-jr-expect "true") 'IL-TRUE)
    ((= char "f") (il-jr-expect "false") 'IL-FALSE)
    ((= char "n") (il-jr-expect "null") nil)
    (T (il-jr-number))
  )
)

;; Parse TEXT; returns the value, or nil with *il-jr-error* set.
(defun il-json-parse (text / result)
  (setq *il-jr-text* text *il-jr-pos* 1 *il-jr-file* nil *il-jr-error* nil)
  (setq result (vl-catch-all-apply 'il-jr-value nil))
  (if (vl-catch-all-error-p result)
    (progn (if (null *il-jr-error*) (setq *il-jr-error* (vl-catch-all-error-message result))) nil)
    result
  )
)

;; Parse the JSON file at PATH; returns the value, or nil with *il-jr-error* set.
(defun il-json-read-file (path / file result)
  (setq *il-jr-error* nil)
  (if (not (setq file (open path "r")))
    (progn (setq *il-jr-error* (strcat "Cannot open " path)) nil)
    (progn
      (setq *il-jr-text* "" *il-jr-pos* 1 *il-jr-file* file)
      (setq result (vl-catch-all-apply 'il-jr-value nil))
      (close file)
      (setq *il-jr-file* nil)
      (if (vl-catch-all-error-p result)
        (progn (if (null *il-jr-error*) (setq *il-jr-error* (vl-catch-all-error-message result))) nil)
        result
      )
    )
  )
)

;; --- Writer -----------------------------------------------------------------------------------

(defun il-jw-string (text / index char code out)
  (setq index 1 out (list "\""))
  (while (<= index (strlen text))
    (setq char (substr text index 1) code (ascii char))
    (setq out
      (cons
        (cond
          ((= char "\"") "\\\"")
          ((= char "\\") "\\\\")
          ((= code 10) "\\n")
          ((= code 13) "\\r")
          ((= code 9) "\\t")
          ((< code 32) " ")
          (T char)
        )
        out
      )
    )
    (setq index (1+ index))
  )
  (apply 'strcat (reverse (cons "\"" out)))
)

;; The JSON text pieces of VALUE, appended in reverse to ACC (callers reverse once).
(defun il-jw-pieces (value acc / first)
  (cond
    ((null value) (cons "null" acc))
    ((eq value 'IL-TRUE) (cons "true" acc))
    ((eq value 'IL-FALSE) (cons "false" acc))
    ((= (type value) 'STR) (cons (il-jw-string value) acc))
    ((= (type value) 'INT) (cons (itoa value) acc))
    ((= (type value) 'REAL) (cons (il-num->str value 6) acc))
    ((il-obj-p value)
      (setq acc (cons "{" acc) first T)
      (foreach pair (cdr value)
        (if (not first) (setq acc (cons "," acc)))
        (setq first nil acc (cons ":" (cons (il-jw-string (car pair)) acc)))
        (setq acc (il-jw-pieces (cdr pair) acc))
      )
      (cons "}" acc)
    )
    ((il-arr-p value)
      (setq acc (cons "[" acc) first T)
      (foreach item (cdr value)
        (if (not first) (setq acc (cons "," acc)))
        (setq first nil acc (il-jw-pieces item acc))
      )
      (cons "]" acc)
    )
    (T (cons (il-jw-string (il-str value)) acc))
  )
)

(defun il-json-text (value)
  (apply 'strcat (reverse (il-jw-pieces value nil)))
)

;; Write VALUE to PATH, a few hundred characters per line so no line is ever too long to read back.
(defun il-json-write-file (value path / file line piece)
  (if (setq file (open path "w"))
    (progn
      (setq line "")
      (foreach piece (reverse (il-jw-pieces value nil))
        (setq line (strcat line piece))
        (if (and (> (strlen line) 200) (member (substr line (strlen line)) '("," "{" "[")))
          (progn (write-line line file) (setq line ""))
        )
      )
      (if (/= line "") (write-line line file))
      (close file)
      T
    )
  )
)
