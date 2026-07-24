import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import toast from "react-hot-toast";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Input } from "../../../components/ui/Input";
import { Modal } from "../../../components/ui/Modal";
import { Select } from "../../../components/ui/Select";
import { useRole } from "../../../hooks/useRole";
import api from "../../../services/api";
import type {
  EvidencePhotoArchiveItem,
  EvidencePhotoFilters,
  PhotoCategory,
} from "../../../types/photoArchive";
import { useProjectWorkspace } from "../../projects/context/ProjectWorkspaceContext";

const directions = ["FRONT", "BACK", "LEFT", "RIGHT", "TOP", "DETAIL", "OTHER"];
const statuses = ["SUBMITTED", "VERIFIED", "REJECTED"];

export const EvidencePhotoArchivePage = () => {
  const params = useParams<{ projectId?: string; id?: string }>();
  const workspace = useProjectWorkspace();
  const projectId = params.projectId || params.id || workspace.projectId;
  const { isAdmin, isProjectManager } = useRole();
  const canManage = isAdmin || isProjectManager;
  const [categories, setCategories] = useState<PhotoCategory[]>([]);
  const [items, setItems] = useState<EvidencePhotoArchiveItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [filters, setFilters] = useState<EvidencePhotoFilters>({ page: 1, pageSize: 24 });
  const [draftSearch, setDraftSearch] = useState("");
  const [selected, setSelected] = useState<EvidencePhotoArchiveItem | null>(null);
  const [categoryName, setCategoryName] = useState("");
  const [showManage, setShowManage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadCategories = useCallback(async () => {
    if (!projectId) return;
    setCategories(await api.photoArchive.categories(projectId, canManage));
  }, [projectId, canManage]);

  const loadPhotos = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.photoArchive.list(projectId, filters);
      setItems(result.items);
      setTotal(result.total);
      setTotalPages(result.totalPages);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to load the evidence archive.");
    } finally {
      setLoading(false);
    }
  }, [projectId, filters]);

  useEffect(() => { loadCategories().catch(() => undefined); }, [loadCategories]);
  useEffect(() => { loadPhotos(); }, [loadPhotos]);

  const setFilter = (key: keyof EvidencePhotoFilters, value: string | number) =>
    setFilters((current) => ({ ...current, [key]: value, page: key === "page" ? Number(value) : 1 }));

  const createCategory = async () => {
    if (!projectId || categoryName.trim().length < 2) return;
    try {
      await api.photoArchive.createCategory(projectId, categoryName.trim());
      setCategoryName("");
      await loadCategories();
      toast.success("Project category created.");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Unable to create category.");
    }
  };

  const deactivate = async (category: PhotoCategory) => {
    if (!projectId) return;
    try {
      await api.photoArchive.deactivateCategory(projectId, category.id);
      await loadCategories();
      toast.success("Category deactivated; historical tags were preserved.");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Unable to deactivate category.");
    }
  };

  if (!projectId) return <Card>No project is selected.</Card>;

  return <div className="page-container space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold">Evidence Photo Archive</h1>
        <p className="text-sm text-muted-foreground">
          Search field photos while retaining their task, submission, uploader, and review provenance.
        </p>
      </div>
      {canManage && <Button variant="outline" onClick={() => setShowManage(true)}>Manage Categories</Button>}
    </div>

    <Card className="space-y-4">
      <form className="flex gap-2" onSubmit={(event) => {
        event.preventDefault();
        setFilter("search", draftSearch.trim());
      }}>
        <Input value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)}
          placeholder="Search task, discipline, category, filename…" />
        <Button type="submit">Search</Button>
      </form>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <Select label="Category" value={filters.category || ""} onChange={(event) => setFilter("category", event.target.value)}
          options={[{ value: "", label: "All categories" }, ...categories.filter((item) => item.active).map((item) => ({ value: item.id, label: item.name }))]} />
        <Input label="Discipline" value={filters.discipline || ""} onChange={(event) => setFilter("discipline", event.target.value)} placeholder="e.g. electrical" />
        <Select label="Status" value={filters.status || ""} onChange={(event) => setFilter("status", event.target.value)}
          options={[{ value: "", label: "All statuses" }, ...statuses.map((value) => ({ value, label: value.toLowerCase() }))]} />
        <Select label="Direction" value={filters.direction || ""} onChange={(event) => setFilter("direction", event.target.value)}
          options={[{ value: "", label: "All directions" }, ...directions.map((value) => ({ value, label: value.toLowerCase() }))]} />
        <Input label="From" type="date" value={filters.dateFrom || ""} onChange={(event) => setFilter("dateFrom", event.target.value)} />
        <Input label="To" type="date" value={filters.dateTo || ""} onChange={(event) => setFilter("dateTo", event.target.value)} />
      </div>
      <div className="flex justify-end">
        <Button variant="ghost" onClick={() => {
          setDraftSearch("");
          setFilters({ page: 1, pageSize: 24 });
        }}>Clear filters</Button>
      </div>
    </Card>

    {error && <Card className="border-destructive/30 text-destructive">{error}</Card>}
    <div className="flex justify-between text-sm text-muted-foreground">
      <span>{total} evidence photo{total === 1 ? "" : "s"}</span>
      {loading && <span>Loading…</span>}
    </div>
    {!loading && !items.length && <Card className="py-12 text-center text-muted-foreground">No evidence photos match these filters.</Card>}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {items.map((photo) => <button key={photo.id} type="button" onClick={() => setSelected(photo)}
        className="overflow-hidden rounded-xl border bg-card text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
        <img src={photo.attachment.fileUrl} alt={photo.attachment.originalFilename} loading="lazy"
          className="aspect-[4/3] w-full bg-muted object-cover" />
        <div className="space-y-2 p-3">
          <div className="flex items-start justify-between gap-2">
            <div><p className="font-semibold">{photo.taskCode}</p><p className="line-clamp-1 text-sm">{photo.taskTitle}</p></div>
            <Badge size="sm" variant={photo.submissionStatus === "VERIFIED" ? "success" : photo.submissionStatus === "REJECTED" ? "danger" : "warning"}>
              {photo.submissionStatus.toLowerCase()}
            </Badge>
          </div>
          <div className="flex flex-wrap gap-1">
            {photo.categories.map((category) => <Badge key={category.id} size="sm" variant="info">{category.name}</Badge>)}
            {!photo.categories.length && <span className="text-xs text-muted-foreground">Uncategorized</span>}
          </div>
          <p className="text-xs text-muted-foreground">
            {photo.discipline || "General"} · {photo.workerName} · {new Date(photo.submissionCreatedAt).toLocaleDateString()}
            {photo.direction ? ` · ${photo.direction.toLowerCase()}` : ""}
          </p>
        </div>
      </button>)}
    </div>

    <div className="flex items-center justify-center gap-3">
      <Button variant="outline" disabled={(filters.page || 1) <= 1} onClick={() => setFilter("page", (filters.page || 1) - 1)}>Previous</Button>
      <span className="text-sm">Page {filters.page || 1} of {Math.max(totalPages, 1)}</span>
      <Button variant="outline" disabled={(filters.page || 1) >= totalPages} onClick={() => setFilter("page", (filters.page || 1) + 1)}>Next</Button>
    </div>

    <Modal isOpen={Boolean(selected)} onClose={() => setSelected(null)} title="Evidence Photo Provenance" size="full">
      {selected && <div className="grid gap-5 md:grid-cols-2">
        <a href={selected.attachment.fileUrl} target="_blank" rel="noreferrer">
          <img src={selected.attachment.fileUrl} alt={selected.attachment.originalFilename} className="max-h-[65vh] w-full rounded-lg bg-muted object-contain" />
        </a>
        <dl className="grid content-start grid-cols-[130px_1fr] gap-2 text-sm">
          <dt className="text-muted-foreground">Task</dt><dd>{selected.taskCode} — {selected.taskTitle}</dd>
          <dt className="text-muted-foreground">Discipline</dt><dd>{selected.discipline || "General"}</dd>
          <dt className="text-muted-foreground">Worker</dt><dd>{selected.workerName}</dd>
          <dt className="text-muted-foreground">Uploader</dt><dd>{selected.uploaderName}</dd>
          <dt className="text-muted-foreground">Submitted</dt><dd>{new Date(selected.submissionCreatedAt).toLocaleString()}</dd>
          <dt className="text-muted-foreground">Status</dt><dd>{selected.submissionStatus}</dd>
          <dt className="text-muted-foreground">Reviewer</dt><dd>{selected.reviewerName || "Not reviewed"}</dd>
          <dt className="text-muted-foreground">Reviewed</dt><dd>{selected.reviewedAt ? new Date(selected.reviewedAt).toLocaleString() : "—"}</dd>
          <dt className="text-muted-foreground">Direction</dt><dd>{selected.direction || "Unlabelled"}</dd>
          <dt className="text-muted-foreground">Categories</dt><dd>{selected.categories.map((item) => item.name).join(", ") || "Uncategorized"}</dd>
          <dt className="text-muted-foreground">Filename</dt><dd className="break-all">{selected.attachment.originalFilename}</dd>
          <dt className="text-muted-foreground">Submission ID</dt><dd className="break-all font-mono text-xs">{selected.fieldSubmissionId}</dd>
        </dl>
      </div>}
    </Modal>

    <Modal isOpen={showManage} onClose={() => setShowManage(false)} title="Project Photo Categories" size="lg">
      <div className="flex gap-2">
        <Input value={categoryName} onChange={(event) => setCategoryName(event.target.value)} placeholder="New project category, e.g. Waterproofing" />
        <Button disabled={categoryName.trim().length < 2} onClick={createCategory}>Add</Button>
      </div>
      <div className="mt-4 max-h-96 space-y-2 overflow-y-auto">
        {categories.map((category) => <div key={category.id} className="flex items-center justify-between rounded border p-3">
          <div><p className="font-medium">{category.name}</p><p className="text-xs text-muted-foreground">{category.isSystem ? "System category" : "Project category"} · {category.active ? "Active" : "Inactive"}</p></div>
          {!category.isSystem && category.active && <Button size="sm" variant="outline" onClick={() => deactivate(category)}>Deactivate</Button>}
        </div>)}
      </div>
    </Modal>
  </div>;
};
