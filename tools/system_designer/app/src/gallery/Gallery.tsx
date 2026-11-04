import { Inbox, Redo2, Settings2, Undo2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import {
  Badge,
  Banner,
  Button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  IconButton,
  Input,
  Kbd,
  LoadBar,
  Menu,
  MenuCheckboxItem,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  Select,
  SeverityIcon,
  Skeleton,
  Tabs,
  ToastProvider,
  Tooltip,
  UnitInput,
  useToast,
} from '../ui';

/** Every component in every state, for review and screenshots (dev server: /gallery.html, SD-1.2). */
export function Gallery() {
  return (
    <ToastProvider>
      <div className="ill-sd sd-gallery" style={{ padding: 24, display: 'grid', gap: 32, maxWidth: 1100 }}>
        <h1>System Designer components</h1>
        <Buttons />
        <Badges />
        <Banners />
        <Fields />
        <Overlays />
        <TabsDemo />
        <Section title="Load bars">
          <LoadBar value={40} max={96} label="PS-1" />
          <LoadBar value={84} max={96} label="PS-2" />
          <LoadBar value={110} max={96} label="PS-3" />
        </Section>
        <Section title="Loading, empty and error">
          <div style={{ display: 'grid', gap: 8, width: 320 }}>
            <Skeleton width="60%" />
            <Skeleton />
            <Skeleton height={80} />
          </div>
          <EmptyState icon={<Inbox size={24} />} title="No runs yet" action={<Button variant="primary">Add a run</Button>}>
            <p>Runs come from your schedule lines. Add one by hand for anything not on the schedule.</p>
          </EmptyState>
          <ErrorState message="The server answered 502" code="INTERNAL" onRetry={() => {}} />
        </Section>
        <Section title="Keyboard">
          <p>
            <Kbd>Ctrl</Kbd> + <Kbd>K</Kbd> commands, <Kbd>?</Kbd> help, <Kbd>[</Kbd> <Kbd>]</Kbd> steps
          </p>
        </Section>
      </div>
    </ToastProvider>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2>{title}</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>{children}</div>
    </section>
  );
}

function Buttons() {
  return (
    <Section title="Buttons">
      <Button variant="primary">Save</Button>
      <Button>Secondary</Button>
      <Button variant="quiet">Quiet</Button>
      <Button variant="danger">Delete run</Button>
      <Button variant="primary" loading>
        Saving
      </Button>
      <Button disabled>Disabled</Button>
      <Button size="sm">Small</Button>
      <IconButton label="Undo" icon={<Undo2 size={18} />} />
      <IconButton label="Redo" icon={<Redo2 size={18} />} disabled />
      <Tooltip content="Tooltips repeat a name; they never hold the only copy">
        <Button variant="quiet">Hover me</Button>
      </Tooltip>
    </Section>
  );
}

function Badges() {
  return (
    <Section title="Badges and severity">
      <Badge>Draft</Badge>
      <Badge tone="info">Revision A</Badge>
      <Badge tone="ok">Approved</Badge>
      <Badge tone="warning">Review required</Badge>
      <Badge tone="error">3 errors</Badge>
      <Badge tone="brand">Engineering</Badge>
      {(['error', 'warning', 'info', 'ok'] as const).map((severity) => (
        <SeverityIcon key={severity} severity={severity} size={20} label />
      ))}
    </Section>
  );
}

function Banners() {
  return (
    <section style={{ display: 'grid', gap: 8 }}>
      <h2>Banners</h2>
      <Banner tone="info" title="Unsaved changes from your last visit were restored." />
      <Banner tone="warning" title="The catalog changed since this design was saved" actions={<Button size="sm">Review</Button>}>
        <p>Two products have new ratings.</p>
      </Banner>
      <Banner tone="error" title="You are offline" onDismiss={() => {}}>
        <p>Changes are kept in this browser and saved when you reconnect.</p>
      </Banner>
      <Banner tone="ok" title="Saved" />
    </section>
  );
}

function Fields() {
  const [length, setLength] = useState(12.5);
  return (
    <Section title="Fields">
      <Field label="Space name" hint="As it appears on the drawings">
        {({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} defaultValue="Kitchen" />}
      </Field>
      <Field label="Location" error="Choose a location rating">
        {({ id, describedBy, invalid }) => (
          <Select id={id} aria-describedby={describedBy} invalid={invalid} defaultValue="">
            <option value="">Choose…</option>
            <option>Dry</option>
            <option>Damp</option>
          </Select>
        )}
      </Field>
      <Field label="Home run length" hint="12.5, 12' 6&quot; or 3.8 m">
        {({ id, describedBy }) => <UnitInput id={id} describedBy={describedBy} value={length} onCommit={setLength} />}
      </Field>
    </Section>
  );
}

function Overlays() {
  const [dialog, setDialog] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [checked, setChecked] = useState(true);
  const toast = useToast();
  return (
    <Section title="Dialogs, menus and toasts">
      <Button onClick={() => setDialog(true)}>Dialog</Button>
      <Button onClick={() => setConfirm(true)}>Confirm</Button>
      <Button onClick={() => setDrawer(true)}>Drawer</Button>
      <Menu trigger={<IconButton label="View" icon={<Settings2 size={18} />} />} label="View">
        <MenuLabel>View</MenuLabel>
        <MenuCheckboxItem checked={checked} onCheckedChange={setChecked}>
          Show checks panel
        </MenuCheckboxItem>
        <MenuSeparator />
        <MenuItem onSelect={() => {}} shortcut="?">
          Help
        </MenuItem>
      </Menu>
      <Button
        onClick={() => toast({ title: 'Run deleted', tone: 'ok', action: { label: 'Undo', onClick: () => {} } })}
      >
        Toast
      </Button>
      <Dialog
        open={dialog}
        onOpenChange={setDialog}
        title="Before you start"
        description="Design aid. Verify against product documentation."
        footer={<Button variant="primary" onClick={() => setDialog(false)}>Accept and continue</Button>}
      >
        <p>Terms text goes here.</p>
      </Dialog>
      <ConfirmDialog
        open={confirm}
        title="Continue with 3 errors?"
        confirmLabel="Continue anyway"
        onConfirm={() => setConfirm(false)}
        onCancel={() => setConfirm(false)}
      >
        <p>You can come back to fix them; the Check step lists them all.</p>
      </ConfirmDialog>
      <Dialog open={drawer} onOpenChange={setDrawer} title="Help" variant="drawer">
        <p>Per-step help, glossary and shortcuts.</p>
      </Dialog>
    </Section>
  );
}

function TabsDemo() {
  const [tab, setTab] = useState('checks');
  return (
    <section style={{ width: 340, border: '1px solid var(--sd-border)', borderRadius: 12 }}>
      <Tabs
        label="Side panel"
        value={tab}
        onValueChange={setTab}
        tabs={[
          { id: 'checks', label: 'Checks', content: <p style={{ padding: 12 }}>Checks list</p> },
          { id: 'history', label: 'History', content: <p style={{ padding: 12 }}>History list</p> },
        ]}
      />
    </section>
  );
}
