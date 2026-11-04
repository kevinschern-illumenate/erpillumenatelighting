import { describe, expect, it } from 'vitest';
import { FIX_STEP, stepForCode } from './checkTargets';
import type { Check } from './open';
import { stepStateLabel, stepStates } from './stepState';

const check = (code: string, severity: Check['severity']): Check => ({
  id: `${code}:x`,
  code,
  ref: 'x',
  severity,
  title: 'x',
  detail: 'x',
});

describe('step states (SD-2.1)', () => {
  it('puts each check on the step that fixes it', () => {
    expect(stepForCode('PSU_OVERLOAD')).toBe('power');
    expect(stepForCode('VD_OVER_TARGET')).toBe('spaces');
    expect(stepForCode('TAPE_RUN_TOO_LONG')).toBe('runs');
    expect(stepForCode('DATA')).toBe('start');
    expect(stepForCode('SOMETHING_NEW')).toBe('check');
    expect(stepForCode(undefined)).toBe('check');
    expect(Object.values(FIX_STEP).every((fix) => fix.label === `Open ${fix.step[0]!.toUpperCase()}${fix.step.slice(1)}`)).toBe(
      true,
    );
  });

  it('shows errors over warnings, and done only once visited', () => {
    const states = stepStates(
      [check('PSU_OVERLOAD', 'error'), check('PSU_ABOVE_DERATE', 'warning'), check('DATA', 'warning'), check('X', 'info')],
      new Set(['start', 'spaces']),
    );
    expect(states.power).toEqual({ status: 'error', errors: 1, warnings: 1 });
    expect(states.start).toEqual({ status: 'warning', errors: 0, warnings: 1 });
    expect(states.spaces.status).toBe('done');
    expect(states.runs.status).toBe('todo');
    expect(states.check.status).toBe('todo');
    expect(stepStateLabel(states.power)).toBe('1 error, 1 warning');
    expect(stepStateLabel(states.spaces)).toBe('done');
    expect(stepStateLabel(states.runs)).toBe('not started');
  });
});
