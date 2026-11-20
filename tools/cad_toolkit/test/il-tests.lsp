;;; il-tests.lsp -- the golden-case runner for real AutoCAD (draw-to-quote plan 3.10).
;;;
;;; accoreconsole loads the toolkit's pure files and this runner (run_tests.scr), which reads
;;; tools/system_designer/fixtures/cad/lisp-subset.json with the toolkit's own JSON reader, runs every
;;; case and writes a PASS/FAIL report. CI runs the same file in tests/portal_unit/test_cad_lisp.py.

(defun il-test-same (expected actual / same)
  (cond
    ((and (null expected) (null actual)) T)
    ((eq expected 'IL-TRUE) (and actual (not (eq actual 'IL-FALSE))))
    ((eq expected 'IL-FALSE) (null actual))
    ((and (numberp expected) (numberp actual)) (equal (float expected) (float actual) 1e-6))
    ((il-arr-p expected)
      (and (listp actual) (= (length (il-items expected)) (length actual))
           (not (member nil (mapcar 'il-test-same (il-items expected) actual)))))
    ((il-obj-p expected)
      (setq same T)
      (foreach pair (cdr expected)
        (if (not (il-test-same (cdr pair) (il-get (car pair) actual))) (setq same nil))
      )
      same
    )
    (T (equal expected actual))
  )
)

(defun il-test-flag (value) (if (eq value 'IL-TRUE) T nil))

(defun il-test-vertices (value)
  (mapcar '(lambda (vertex) (mapcar 'float (il-items vertex))) (il-items value))
)

;; Counts one case into the PASSED/FAILED/FILE of the running il-run-golden (dynamic scope).
(defun il-test-check (group number expected actual)
  (if (il-test-same expected actual)
    (setq passed (1+ passed))
    (progn
      (setq failed (1+ failed))
      (write-line (strcat "FAIL " group " " (itoa number) ": expected " (il-json-text expected)) file)
    )
  )
)

;; Run every golden case; write REPORT-PATH; return (passed failed).
(defun il-run-golden (fixture-path report-path / cases file passed failed index)
  (setq cases (il-json-read-file fixture-path) passed 0 failed 0)
  (setq file (open report-path "w"))
  (if (null cases)
    (progn (write-line (strcat "ERROR could not read " fixture-path ": " (il-str *il-jr-error*)) file) (setq failed 1))
    (progn
      (setq index 0)
      (foreach case (il-items (il-j cases "cut_snap"))
        (il-test-check "cut_snap" (setq index (1+ index)) (il-j case "expected")
          (il-cut-snap (float (il-j case "length_in")) (il-j case "cut_mm") (il-test-flag (il-j case "free_cut")))))
      (setq index 0)
      (foreach case (il-items (il-j cases "run_split"))
        (il-test-check "run_split" (setq index (1+ index)) (il-j case "expected")
          (il-run-split (float (il-j case "length_in")) (il-j case "w_per_ft") (il-j case "cut_mm")
                        (il-test-flag (il-j case "free_cut")) (il-j case "max_run_vd_ft") (il-j case "override_ft"))))
      (setq index 0)
      (foreach case (il-items (il-j cases "psu_load"))
        (il-test-check "psu_load" (setq index (1+ index)) (il-j case "expected")
          (il-psu-load (il-items (il-j case "loads_w")) (il-j case "rated_w") (il-j case "usable_load_factor"))))
      (setq index 0)
      (foreach case (il-items (il-j cases "path_length"))
        (il-test-check "path_length" (setq index (1+ index)) (il-j case "expected")
          (il-path-length (il-test-vertices (il-j case "vertices")) (il-test-flag (il-j case "closed")))))
    )
  )
  (write-line (strcat "ilLumenate CAD toolkit " *il-version* ": " (itoa passed) " passed, " (itoa failed) " failed") file)
  (close file)
  (list passed failed)
)
