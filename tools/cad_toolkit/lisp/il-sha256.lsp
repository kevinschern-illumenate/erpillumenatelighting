;;; il-sha256.lsp -- ilLumenate CAD toolkit: SHA-256 in plain AutoLISP.
;;;
;;; The ilq/2 package carries a drawing hash ("sha256:..."), used to tell whether the drawing changed
;;; since its last import (ILCHECK, ILSTRIP). AutoLISP has no hash function, so this is FIPS 180-4
;;; on 32-bit words. Sums go through 16-bit halves so no integer ever overflows. Input is ASCII text
;;; (the model's JSON). Pure: CI checks it against Python's hashlib.

(setq *il-sha-k*
  '(1116352408 1899447441 -1245643825 -373957723 961987163 1508970993 -1841331548 -1424204075
    -670586216 310598401 607225278 1426881987 1925078388 -2132889090 -1680079193 -1046744716
    -459576895 -272742522 264347078 604807628 770255983 1249150122 1555081692 1996064986
    -1740746414 -1473132947 -1341970488 -1084653625 -958395405 -710438585 113926993 338241895
    666307205 773529912 1294757372 1396182291 1695183700 1986661051 -2117940946 -1838011259
    -1564481375 -1474664885 -1035236496 -949202525 -778901479 -694614492 -200395387 275423344
    430227734 506948616 659060556 883997877 958139571 1322822218 1537002063 1747873779
    1955562222 2024104815 -2067236844 -1933114872 -1866530822 -1538233109 -1090935817 -965641998)
)

(defun il-sha-add (a b / low high)
  (setq low (+ (logand a 65535) (logand b 65535))
        high (+ (logand (lsh a -16) 65535) (logand (lsh b -16) 65535) (lsh low -16)))
  (logior (lsh (logand high 65535) 16) (logand low 65535))
)

(defun il-sha-add-all (values / total)
  (setq total 0)
  (foreach value values (setq total (il-sha-add total value)))
  total
)

(defun il-sha-rotr (x n)
  (logior (lsh x (- n)) (lsh x (- 32 n)))
)

(defun il-sha-xor (a b) (boole 6 a b))

(defun il-sha-hex (word / text index nibble)
  (setq text "" index 7)
  (while (>= index 0)
    (setq nibble (logand (lsh word (* -4 index)) 15))
    (setq text (strcat text (substr "0123456789abcdef" (1+ nibble) 1)) index (1- index))
  )
  text
)

;; The bytes of TEXT padded to whole 64-byte blocks, as a list of 32-bit words.
(defun il-sha-words (text / bytes count index word words bits)
  (setq count (strlen text) index 1)
  (while (<= index count)
    (setq bytes (cons (logand (ascii (substr text index 1)) 255) bytes) index (1+ index))
  )
  (setq bytes (cons 128 bytes))
  (while (/= (rem (length bytes) 64) 56) (setq bytes (cons 0 bytes)))
  (setq bits (* count 8))
  ;; 64-bit big-endian length; texts stay far below 2^29 bytes, so the high word is zero.
  (setq bytes (append (list (logand bits 255) (logand (lsh bits -8) 255) (logand (lsh bits -16) 255)
                            (logand (lsh bits -24) 255) 0 0 0 0)
                      bytes))
  (setq bytes (reverse bytes))
  (while bytes
    (setq word (logior (lsh (car bytes) 24) (lsh (cadr bytes) 16) (lsh (caddr bytes) 8) (cadddr bytes)))
    (setq words (cons word words) bytes (cddddr bytes))
  )
  (reverse words)
)

(defun il-sha256 (text / h words w index a b c d e f g hh s0 s1 ch maj t1 t2 block)
  (setq h '(1779033703 -1150833019 1013904242 -1521486534 1359893119 -1694144372 528734635 1541459225))
  (setq words (il-sha-words text))
  (while words
    (setq w nil index 0)
    (repeat 16 (setq w (cons (car words) w) words (cdr words)))
    (setq w (reverse w) index 16)
    (while (< index 64)
      (setq s0 (il-sha-xor (il-sha-xor (il-sha-rotr (nth (- index 15) w) 7) (il-sha-rotr (nth (- index 15) w) 18))
                           (lsh (nth (- index 15) w) -3)))
      (setq s1 (il-sha-xor (il-sha-xor (il-sha-rotr (nth (- index 2) w) 17) (il-sha-rotr (nth (- index 2) w) 19))
                           (lsh (nth (- index 2) w) -10)))
      (setq w (append w (list (il-sha-add-all (list (nth (- index 16) w) s0 (nth (- index 7) w) s1))))
            index (1+ index))
    )
    (setq a (nth 0 h) b (nth 1 h) c (nth 2 h) d (nth 3 h) e (nth 4 h) f (nth 5 h) g (nth 6 h) hh (nth 7 h) index 0)
    (while (< index 64)
      (setq s1 (il-sha-xor (il-sha-xor (il-sha-rotr e 6) (il-sha-rotr e 11)) (il-sha-rotr e 25)))
      (setq ch (il-sha-xor (logand e f) (logand (~ e) g)))
      (setq t1 (il-sha-add-all (list hh s1 ch (nth index *il-sha-k*) (nth index w))))
      (setq s0 (il-sha-xor (il-sha-xor (il-sha-rotr a 2) (il-sha-rotr a 13)) (il-sha-rotr a 22)))
      (setq maj (il-sha-xor (il-sha-xor (logand a b) (logand a c)) (logand b c)))
      (setq t2 (il-sha-add s0 maj))
      (setq hh g g f f e e (il-sha-add d t1) d c c b b a a (il-sha-add t1 t2) index (1+ index))
    )
    (setq h (mapcar 'il-sha-add h (list a b c d e f g hh)))
  )
  (apply 'strcat (mapcar 'il-sha-hex h))
)
