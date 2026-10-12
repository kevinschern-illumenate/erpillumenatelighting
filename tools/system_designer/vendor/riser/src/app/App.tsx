import { lazy, Suspense, useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useStore } from 'zustand';
import {
  ArrowUpRight,
  BookOpen,
  Boxes,
  Cable,
  ChevronRight,
  CircleHelp,
  FileDown,
  FileText,
  FolderOpen,
  Library,
  Moon,
  PanelsTopLeft,
  Plus,
  Redo2,
  Save,
  Sun,
  Undo2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProjectPage } from '@/features/project/ProjectPage';
import { useWorkspace } from '@/hooks/use-workspace';
import { useProjectStore } from '@/state/project-store';
import { useLibraryStore } from '@/state/library-store';
import { useLibraryWorkspace } from '@/hooks/use-library-workspace';
const TablesPage = lazy(() =>
  import('@/features/tables/TablesPage').then((m) => ({ default: m.TablesPage })),
);
const ReviewPage = lazy(() =>
  import('@/features/review/ReviewPage').then((m) => ({ default: m.ReviewPage })),
);
const LibraryPage = lazy(() =>
  import('@/features/library/LibraryPage').then((m) => ({ default: m.LibraryPage })),
);
const DrawingPage = lazy(() =>
  import('@/features/drawing/DrawingPage').then((m) => ({ default: m.DrawingPage })),
);
const ExportPage = lazy(() =>
  import('@/features/export/ExportPage').then((m) => ({ default: m.ExportPage })),
);

const navigation = [
  { path: 'project', label: 'Project', icon: FileText, step: '01' },
  { path: 'tables', label: 'Tables', icon: Boxes, step: '02' },
  { path: 'review', label: 'Review', icon: Cable, step: '03' },
  { path: 'drawing', label: 'Drawing', icon: PanelsTopLeft, step: '04' },
  { path: 'export', label: 'Export', icon: FileDown, step: '05' },
];

export function App() {
  const workspace = useWorkspace();
  useLibraryWorkspace();
  const draft = useProjectStore((s) => s.draft);
  const canUndo = useStore(useProjectStore.temporal, (s) => s.pastStates.length > 0);
  const canRedo = useStore(useProjectStore.temporal, (s) => s.futureStates.length > 0);
  const path = useLocation().pathname.slice(1);
  const libraryCanUndo = useStore(useLibraryStore.temporal, (s) => s.pastStates.length > 0);
  const libraryCanRedo = useStore(useLibraryStore.temporal, (s) => s.futureStates.length > 0);
  const history = () =>
    path === 'libraries'
      ? useLibraryStore.temporal.getState()
      : useProjectStore.temporal.getState();
  const currentLabel = navigation.find((item) => item.path === path)?.label ?? 'Libraries';
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem('riser-theme') === 'dark';
    } catch {
      return false;
    }
  });
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    try {
      localStorage.setItem('riser-theme', dark ? 'dark' : 'light');
    } catch {
      /* Theme remains usable when preferences cannot persist. */
    }
  }, [dark]);

  useEffect(() => {
    if (!workspace.ready) return;
    const handler = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      // The library JSON buffer has native text history separate from project edits.
      if (e.target instanceof HTMLElement && e.target.classList.contains('json-editor')) return;
      const history =
        path === 'libraries'
          ? useLibraryStore.temporal.getState()
          : useProjectStore.temporal.getState();
      if (e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) history.redo();
        else history.undo();
      }
      if (e.key.toLowerCase() === 'y') {
        e.preventDefault();
        history.redo();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [workspace.ready, path]);

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <div className="brand">
          <img
            className="brand-logo"
            src="/brand/illumenate-main-white.svg"
            alt="ilLumenate Lighting"
            width="180"
            height="120"
          />
          <span className="brand-product">RISER WORKSPACE</span>
        </div>
        <Button
          className="new-project"
          variant="outline"
          onClick={() => void workspace.create()}
          disabled={!workspace.ready}
        >
          <Plus /> New project
        </Button>
        <div className="nav-eyebrow">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ path, label, icon: Icon, step }) => (
            <NavLink
              to={`/${path}`}
              key={path}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={19} />
              <span>{label}</span>
              <span className="nav-step">{step}</span>
            </NavLink>
          ))}
        </nav>
        <div className="nav-divider" />
        <NavLink
          to="/libraries"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <Library size={19} />
          <span>Libraries</span>
          <ArrowUpRight size={15} />
        </NavLink>
        <div className="recent-projects">
          <div className="nav-eyebrow">RECENT PROJECTS</div>
          {workspace.recent.length ? (
            workspace.recent.slice(0, 5).map((item) => (
              <button
                key={item.id}
                disabled={item.id === draft.id || !workspace.ready}
                title={item.draft.meta.name || 'Untitled project'}
                onClick={() => void workspace.open(item.draft)}
              >
                <FolderOpen size={15} />
                <span>{item.draft.meta.name || 'Untitled project'}</span>
                {item.id === draft.id && <span className="current-dot" />}
              </button>
            ))
          ) : (
            <p>Your saved drafts appear here.</p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="phase-badge">
            <span>01</span>
            <div>
              Engineering workspace<small>Local riser design</small>
            </div>
          </div>
          <button
            className="help-button"
            onClick={() => setShowHelp(!showHelp)}
            aria-expanded={showHelp}
          >
            <CircleHelp size={17} /> Review guide <ChevronRight size={16} />
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{currentLabel}</strong>
          </div>
          <div className="topbar-actions">
            <span className={`save-status ${workspace.status}`} role="status">
              <span />
              {workspace.status === 'saved'
                ? 'Saved locally'
                : workspace.status === 'error'
                  ? 'Storage needs attention'
                  : 'Saving…'}
            </span>
            <span className="toolbar-divider" />
            <Button
              variant="ghost"
              size="icon"
              title="Undo (Ctrl+Z)"
              aria-label="Undo"
              disabled={!(path === 'libraries' ? libraryCanUndo : canUndo) || !workspace.ready}
              onClick={() => history().undo()}
            >
              <Undo2 />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Redo (Ctrl+Shift+Z)"
              aria-label="Redo"
              disabled={!(path === 'libraries' ? libraryCanRedo : canRedo) || !workspace.ready}
              onClick={() => history().redo()}
            >
              <Redo2 />
            </Button>
            <span className="toolbar-divider" />
            <Button
              variant="ghost"
              size="icon"
              title={dark ? 'Light mode' : 'Dark mode'}
              aria-label={dark ? 'Use light mode' : 'Use dark mode'}
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun /> : <Moon />}
            </Button>
          </div>
        </header>
        <main id="main-content" tabIndex={-1}>
          <div className="page-heading">
            <div>
              <div className="eyebrow">LIGHTING SYSTEMS / {currentLabel.toUpperCase()}</div>
              <h1>{currentLabel === 'Project' ? 'Project setup' : currentLabel}</h1>
              <p>
                {currentLabel === 'Project'
                  ? 'Set the context for your next riser.'
                  : 'Your lighting system workspace.'}
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() => void workspace.persist().catch(() => undefined)}
              disabled={!workspace.ready}
            >
              <Save /> {path === 'libraries' ? 'Save project' : 'Save now'}
            </Button>
          </div>
          {showHelp && (
            <section className="help-panel">
              <BookOpen size={22} />
              <div>
                <h2>Design a riser</h2>
                <p>
                  Set project details, add sources, equipment and loads in Tables, then inspect
                  calculations and warnings in Review. Tables includes a complete example to
                  explore.
                </p>
                <p>
                  Open Drawing to pan, zoom and pin devices. Export vector PDF, native DXF and CSV
                  schedules. Save a project file and a library backup when transferring work.
                  Product seeds are examples; replace their specifications with verified
                  manufacturer data.
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setShowHelp(false)}>
                Close
              </Button>
            </section>
          )}
          {workspace.error && (
            <div className="error-banner" role="alert">
              {workspace.error}
              {!workspace.ready && (
                <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
                  Retry
                </Button>
              )}
            </div>
          )}
          {!workspace.ready ? (
            <div className="panel loading-panel">
              {workspace.error ? 'Workspace recovery required.' : 'Opening local workspace…'}
            </div>
          ) : (
            <Suspense fallback={<div className="panel loading-panel">Opening workspace…</div>}>
              <Routes>
                <Route path="/project" element={<ProjectPage />} />
                <Route path="/tables" element={<TablesPage />} />
                <Route path="/review" element={<ReviewPage />} />
                <Route path="/drawing" element={<DrawingPage />} />
                <Route path="/export" element={<ExportPage />} />
                <Route path="/libraries" element={<LibraryPage />} />
                <Route path="*" element={<Navigate to="/project" replace />} />
              </Routes>
            </Suspense>
          )}
          <footer className="page-footer">
            <span>ilLumenate Lighting Riser Generator</span>
            <span>
              LOCAL WORKSPACE <span className="footer-dot">·</span> v1.2.0
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
