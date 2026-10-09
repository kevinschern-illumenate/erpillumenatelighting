import { ArrowUpRight, FileText, SlidersHorizontal } from 'lucide-react';
import type { ReactNode } from 'react';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { ProjectSettingsSchema } from '@/schemas/project';
import { DraftSchema } from '@/schemas/workspace';
import { useProjectStore } from '@/state/project-store';
import { AdvancedProject } from './AdvancedProject';

function Field({
  id,
  label,
  hint,
  children,
  wide = false,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={wide ? 'field field-wide' : 'field'}>
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  );
}

export function ProjectPage() {
  const { draft, editMeta, editSetting, editNote } = useProjectStore();
  const { meta, settings } = draft;
  const textFields = [
    ['name', 'Project name', 'Untitled project', 160],
    ['number', 'Project number', 'e.g. 26-104', 80],
    ['client', 'Client', 'Client or organization', 160],
    ['siteAddress', 'Site address', 'Street, city, state', 300],
    ['designer', 'Drawn by', 'Name or initials', 100],
    ['checker', 'Checked by', 'Name or initials', 100],
  ] as const;
  return (
    <>
      <div className="project-layout">
        <div className="project-main">
          <section className="panel">
            <div className="panel-heading">
              <div className="section-icon">
                <FileText size={18} />
              </div>
              <div>
                <h2>Project information</h2>
                <p>Details for your drawing set.</p>
              </div>
              <span className="section-number">01</span>
            </div>
            <div className="form-grid">
              {textFields.map(([key, label, placeholder, maxLength]) => (
                <Field
                  key={key}
                  id={key}
                  label={label}
                  wide={key === 'name' || key === 'siteAddress'}
                >
                  <Input
                    id={key}
                    value={meta[key]}
                    maxLength={maxLength}
                    placeholder={placeholder}
                    autoComplete="off"
                    onChange={(e) => editMeta(key, e.target.value)}
                  />
                </Field>
              ))}
              <Field id="date" label="Issue date">
                <Input
                  id="date"
                  type="date"
                  value={meta.date}
                  onChange={(e) => {
                    if (DraftSchema.shape.meta.shape.date.safeParse(e.target.value).success)
                      editMeta('date', e.target.value);
                  }}
                />
              </Field>
              <Field id="brand" label="Brand">
                <Select
                  id="brand"
                  value={meta.brand}
                  options={[
                    { value: 'illumenate', label: 'ilLumenate Lighting' },
                    { value: '206', label: '206 Lighting' },
                  ]}
                  onValueChange={(value) =>
                    editMeta('brand', DraftSchema.shape.meta.shape.brand.parse(value))
                  }
                />
              </Field>
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <div className="section-icon">
                <SlidersHorizontal size={18} />
              </div>
              <div>
                <h2>Drawing defaults</h2>
                <p>Your starting standards for this project.</p>
              </div>
              <span className="section-number">02</span>
            </div>
            <div className="form-grid defaults-grid">
              <Field id="sheet-size" label="Sheet size">
                <Select
                  id="sheet-size"
                  value={settings.sheet.size}
                  options={[
                    { value: 'ARCH_D', label: 'ARCH D · 36 × 24 in' },
                    { value: 'ARCH_C', label: 'ARCH C · 24 × 18 in' },
                    { value: 'ANSI_B', label: 'ANSI B · 17 × 11 in' },
                    { value: 'ANSI_D', label: 'ANSI D · 34 × 22 in' },
                  ]}
                  onValueChange={(v) =>
                    editSetting('sheet', {
                      ...settings.sheet,
                      size: ProjectSettingsSchema.shape.sheet.unwrap().shape.size.parse(v),
                    })
                  }
                />
              </Field>
              <Field
                id="sheet-prefix"
                label="Sheet prefix"
                hint={`First sheet: ${meta.sheetPrefix}1`}
              >
                <Input
                  id="sheet-prefix"
                  value={meta.sheetPrefix}
                  maxLength={12}
                  onChange={(e) => {
                    if (e.target.value.length) editMeta('sheetPrefix', e.target.value);
                  }}
                />
              </Field>
              <Field id="flow" label="Power flow">
                <Select
                  id="flow"
                  value={settings.sheet.flow}
                  options={[
                    { value: 'LR', label: 'Left to right' },
                    { value: 'TB', label: 'Top to bottom' },
                  ]}
                  onValueChange={(v) =>
                    editSetting('sheet', {
                      ...settings.sheet,
                      flow: ProjectSettingsSchema.shape.sheet.unwrap().shape.flow.parse(v),
                    })
                  }
                />
              </Field>
              <Field
                id="psu"
                label="PSU loading limit"
                hint="Warning threshold for each power-supply output."
              >
                <div className="input-suffix">
                  <Input
                    id="psu"
                    type="number"
                    min={1}
                    max={100}
                    value={settings.psuDeratePct}
                    onChange={(e) => {
                      const value = e.target.valueAsNumber;
                      if (Number.isFinite(value) && value >= 1 && value <= 100)
                        editSetting('psuDeratePct', value);
                    }}
                  />
                  <span>%</span>
                </div>
              </Field>
              <Field id="stamp" label="Issue stamp" wide>
                <Select
                  id="stamp"
                  value={meta.stamp}
                  options={['PRELIMINARY', 'FOR REFERENCE', 'NOT FOR CONSTRUCTION', 'NONE'].map(
                    (v) => ({ value: v, label: v === 'NONE' ? 'No stamp' : v }),
                  )}
                  onValueChange={(v) =>
                    editMeta('stamp', DraftSchema.shape.meta.shape.stamp.parse(v))
                  }
                />
              </Field>
            </div>
          </section>
          <section className="panel notes-panel">
            <label htmlFor="scratch-note">
              <h2>Project scratchpad</h2>
            </label>
            <p>Internal notes saved with this draft.</p>
            <textarea
              id="scratch-note"
              rows={3}
              maxLength={4000}
              placeholder="Add project context or items to resolve…"
              value={draft.scratchNote}
              onChange={(e) => editNote(e.target.value)}
            />
          </section>
        </div>
        <aside className="project-aside">
          <section className="standards-card">
            <div className="eyebrow">DRAWING SET</div>
            <div className="sheet-reference">
              <span>{meta.sheetPrefix}1</span>
              <ArrowUpRight size={24} />
            </div>
            <p className="sheet-project">{meta.name || 'Untitled project'}</p>
            <dl>
              <div>
                <dt>Format</dt>
                <dd>{settings.sheet.size.replace('_', ' ')}</dd>
              </div>
              <div>
                <dt>Orientation</dt>
                <dd>Landscape</dd>
              </div>
              <div>
                <dt>Flow</dt>
                <dd>{settings.sheet.flow === 'LR' ? 'Left → right' : 'Top → bottom'}</dd>
              </div>
              <div>
                <dt>Brand</dt>
                <dd>{meta.brand === 'illumenate' ? 'ilLumenate Lighting' : '206 Lighting'}</dd>
              </div>
            </dl>
            <div className="stamp-label">{meta.stamp === 'NONE' ? 'NO STAMP' : meta.stamp}</div>
            <p className="standards-footnote">Open Drawing for the live sheet preview.</p>
          </section>
          <section className="review-note">
            <span className="eyebrow">LIBRARY SETUP</span>
            <h3>Explore the seed libraries.</h3>
            <p>
              Open Libraries for example products, wire templates and editable code tables. Project
              edits still support Undo and Redo.
            </p>
            <div className="shortcut">
              <kbd>Ctrl</kbd>
              <span>+</span>
              <kbd>Z</kbd>
              <span>Undo</span>
            </div>
            <div className="shortcut">
              <kbd>Ctrl</kbd>
              <span>+</span>
              <kbd>Shift</kbd>
              <span>+</span>
              <kbd>Z</kbd>
              <span>Redo</span>
            </div>
            <p className="muted">On Mac, use ⌘ instead of Ctrl.</p>
          </section>
          <div className="local-note">
            <span className="local-marker" />
            <p>
              Saved in this browser on this device. Keep the same localhost address to reopen your
              drafts.
            </p>
          </div>
        </aside>
      </div>
      <AdvancedProject />
    </>
  );
}
