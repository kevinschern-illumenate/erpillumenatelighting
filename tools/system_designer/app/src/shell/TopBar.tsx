import { ChevronDown, ChevronRight, CircleAlert, CircleCheck, CloudOff, HelpCircle, LoaderCircle, Redo2, Save, Undo2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { PRODUCT_NAME } from '../product';
import { Badge, Button, IconButton, Menu, MenuCheckboxItem, MenuItem, MenuLabel, MenuSeparator, type Tone } from '../ui';
import type { Mode } from './steps';

/** The five things the save indicator can say (SD-1.4). */
export type SaveTone = 'saved' | 'saving' | 'dirty' | 'offline' | 'error';

const SAVE_ICON: Record<SaveTone, ReactNode> = {
  saved: <CircleCheck size={16} aria-hidden />,
  saving: <LoaderCircle size={16} aria-hidden className="sd-spin" />,
  dirty: <span className="sd-save__dot" aria-hidden />,
  offline: <CloudOff size={16} aria-hidden />,
  error: <CircleAlert size={16} aria-hidden />,
};

export function SaveIndicator({ tone, text }: { tone: SaveTone; text: string }) {
  return (
    <span className={`sd-save sd-save--${tone}`}>
      {SAVE_ICON[tone]}
      <span role="status" data-testid="save-state">
        {text}
      </span>
    </span>
  );
}

export interface TopBarProps {
  scheduleUrl: string;
  projectUrl: string | null;
  projectName: string | null;
  title: string;
  version: number;
  revision: string | null;
  status: string | null;
  review: { label: string; tone: Tone };
  save: { tone: SaveTone; text: string };
  readOnly: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onUndo(): void;
  onRedo(): void;
  canSave: boolean;
  saving: boolean;
  onSave(): void;
  mode: Mode;
  onMode(mode: Mode): void;
  engineeringAvailable: boolean;
  /** Dealers choose to show the engineering tools; staff always have them. */
  optIn: { checked: boolean; onChange(value: boolean): void } | null;
  panelOpen: boolean;
  onPanel(open: boolean): void;
  onHelp(): void;
  onShortcuts(): void;
  onPalette(): void;
}

/** One row with where you are, the design's state, and the actions that apply everywhere (SD-1.3). */
export function TopBar(props: TopBarProps) {
  const { mode, readOnly } = props;
  return (
    <header className="sd-topbar">
      <div className="sd-topbar__where">
        <nav aria-label="Breadcrumb" className="sd-crumbs">
          <ol>
            <li>
              <a href="/portal/projects">Projects</a>
            </li>
            {props.projectUrl && props.projectName ? (
              <li>
                <ChevronRight size={14} aria-hidden className="sd-crumbs__sep" />
                <a href={props.projectUrl}>{props.projectName}</a>
              </li>
            ) : null}
            <li>
              <ChevronRight size={14} aria-hidden className="sd-crumbs__sep" />
              <span data-testid="schedule-name">
                <a href={props.scheduleUrl}>{props.title}</a> · Version {props.version}
              </span>
            </li>
            <li aria-current="page">
              <ChevronRight size={14} aria-hidden className="sd-crumbs__sep" />
              {props.revision ? `Revision ${props.revision}` : 'New design'}
            </li>
          </ol>
        </nav>
        <div className="sd-topbar__title-row">
          <h1 className="ill-sd__title sd-topbar__title">{PRODUCT_NAME}</h1>
          {props.status ? <Badge tone={props.status === 'Approved' ? 'ok' : 'neutral'}>{props.status}</Badge> : null}
          <Badge tone={props.review.tone} data-testid="review-chip">
            {props.review.label}
          </Badge>
        </div>
      </div>
      <div className="sd-topbar__actions">
        <SaveIndicator {...props.save} />
        <div className="sd-topbar__group">
          <IconButton
            label="Undo"
            shortcut="Ctrl+Z"
            icon={<Undo2 size={18} />}
            variant="quiet"
            disabled={readOnly || !props.canUndo}
            onClick={props.onUndo}
          />
          <IconButton
            label="Redo"
            shortcut="Ctrl+Y"
            icon={<Redo2 size={18} />}
            variant="quiet"
            disabled={readOnly || !props.canRedo}
            onClick={props.onRedo}
          />
        </div>
        {props.engineeringAvailable ? (
          <div className="sd-segmented" role="group" aria-label="Mode">
            {(['guided', 'engineering'] as const).map((value) => (
              <button key={value} type="button" aria-pressed={mode === value} onClick={() => props.onMode(value)}>
                {value === 'guided' ? 'Guided' : 'Engineering'}
              </button>
            ))}
          </div>
        ) : null}
        <Menu
          label="View"
          align="end"
          trigger={
            <Button variant="quiet" size="sm">
              View <ChevronDown size={14} aria-hidden />
            </Button>
          }
        >
          {props.optIn ? (
            <>
              <MenuCheckboxItem checked={props.optIn.checked} onCheckedChange={props.optIn.onChange}>
                Engineering tools
              </MenuCheckboxItem>
              <MenuSeparator />
            </>
          ) : null}
          <MenuCheckboxItem checked={props.panelOpen} onCheckedChange={props.onPanel}>
            Checks panel
          </MenuCheckboxItem>
          <MenuSeparator />
          <MenuLabel>Go</MenuLabel>
          <MenuItem onSelect={props.onPalette} shortcut="Ctrl+K">
            Find a step or check…
          </MenuItem>
          <MenuItem onSelect={props.onShortcuts} shortcut="?">
            Keyboard shortcuts
          </MenuItem>
        </Menu>
        <Button variant="quiet" size="sm" icon={<HelpCircle size={16} />} onClick={props.onHelp}>
          Help
        </Button>
        <Button
          variant="primary"
          icon={<Save size={16} />}
          disabled={!props.canSave}
          loading={props.saving}
          onClick={props.onSave}
          title="Save (Ctrl+S)"
        >
          Save
        </Button>
      </div>
    </header>
  );
}
