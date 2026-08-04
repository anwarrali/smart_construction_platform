import { useEffect, useMemo, useState } from "react";
import { CheckSquare, Download, Search, Square } from "lucide-react";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import api from "../../../services/api";
import type { IFCElement, IFCFinding, IFCSpatialNode } from "../../../types/ifc";
import { displayValue, EmptyState, ErrorState, labelize, LoadingState, SourceBadge } from "./IFCShared";

interface Filters { q: string; discipline: string; storeyId: string; entityType: string; elementType: string; material: string; system: string; classification: string; completeness: string; issueSeverity: string; sortBy: string; sortDirection: "asc" | "desc" }
const initialFilters: Filters = { q: "", discipline: "", storeyId: "", entityType: "", elementType: "", material: "", system: "", classification: "", completeness: "", issueSeverity: "", sortBy: "name", sortDirection: "asc" };
const selectClass = "rounded-md border bg-background px-3 py-2 text-sm";

const csvCell = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
const classificationLabel = (element: IFCElement) => element.metadataJson?.classifications?.map((item) => [item.system, item.code, item.name].filter(Boolean).join(" · ")).join("; ") || "Not classified in source IFC";

const inferQuantityUnit = (name: string, units?: Record<string, string>) => {
  const lowered = name.toLowerCase();
  if (lowered.includes("area")) return units?.AREAUNIT || "m²";
  if (lowered.includes("volume")) return units?.VOLUMEUNIT || "m³";
  if (lowered.includes("weight") || lowered.includes("mass")) return units?.MASSUNIT || "kg";
  if (["count", "number"].some((word) => lowered.includes(word))) return "count";
  if (["length", "width", "height", "perimeter", "depth"].some((word) => lowered.includes(word))) return units?.LENGTHUNIT || "m";
  return "";
};

const ReadableRows = ({ value, quantities = false, units }: { value: Record<string, unknown>; quantities?: boolean; units?: Record<string, string> }) => {
  if (!Object.keys(value || {}).length) return <p className="text-sm text-muted-foreground">Not defined in source IFC.</p>;
  return <div className="space-y-3">{Object.entries(value).map(([setName, setValue]) => <div key={setName} className="rounded-lg border"><div className="border-b bg-muted/40 px-3 py-2 text-sm font-semibold">{setName}</div><div className="divide-y">{setValue && typeof setValue === "object" && !Array.isArray(setValue) ? Object.entries(setValue as Record<string, unknown>).filter(([key]) => key !== "id").map(([name, item]) => <div key={name} className="grid grid-cols-[minmax(130px,1fr)_2fr] gap-3 px-3 py-2 text-sm"><span className="text-muted-foreground">{labelize(name)}</span><span>{displayValue(item && typeof item === "object" && "value" in item ? (item as { value: unknown }).value : item)} {quantities && <small className="text-muted-foreground">{inferQuantityUnit(name, units)}</small>}</span></div>) : <div className="px-3 py-2 text-sm">{displayValue(setValue)}</div>}</div></div>)}</div>;
};

const ElementDetails = ({ element, nodes, issueCount, onFocus3D }: { element?: IFCElement; nodes: IFCSpatialNode[]; issueCount: number; onFocus3D?:(id:string)=>void }) => {
  if (!element) return <EmptyState title="Select an element" description="Open an element to inspect identity, location, classification, materials, properties, quantities and relationships."/>;
  const nodeName = (id?: string) => nodes.find((node) => node.id === id)?.name;
  const fields = (items: Array<[string, unknown]>) => <div className="grid gap-3 sm:grid-cols-2">{items.map(([label, value]) => <div key={label}><p className="text-xs text-muted-foreground">{label}</p><p className="break-words text-sm font-medium">{displayValue(value)}</p></div>)}</div>;
  const materialStatus = element.metadataJson?.materialStatus;
  return <div className="space-y-4">
    <Card><div className="flex items-center justify-between"><h2 className="font-semibold">Identity</h2><Badge variant={issueCount ? "warning" : "success"}>{issueCount} issues</Badge></div><div className="mt-4">{fields([["Original IFC name", element.metadataJson?.originalName || element.name], ["Description", element.description], ["IFC class", element.entityType], ["Predefined type", element.predefinedType], ["Object type", element.objectType], ["Element type", element.typeName], ["Tag", element.tag], ["GlobalId", element.globalId]])}</div><Button className="mt-4" size="sm" onClick={()=>onFocus3D?.(element.id)}>Focus in 3D</Button></Card>
    <Card><h2 className="font-semibold">Location</h2><div className="mt-4">{fields([["Building", nodeName(element.buildingNodeId)], ["Storey", nodeName(element.storeyNodeId)], ["Space", nodeName(element.spaceNodeId)], ["Zone", nodeName(element.zoneNodeId)], ["Coordinates", element.boundingBoxJson ? "Geometry bounds available" : undefined]])}</div></Card>
    <Card><div className="flex items-center justify-between"><h2 className="font-semibold">Classification</h2><SourceBadge source={element.metadataJson?.classifications?.[0]?.source || element.metadataJson?.disciplineSource}/></div><p className="mt-3 text-sm">{classificationLabel(element)}</p><div className="mt-3">{fields([["Discipline", labelize(element.discipline)], ["Confidence", `${Math.round((element.metadataJson?.disciplineConfidence || 0) * 100)}%`], ["Reason", element.metadataJson?.disciplineReason], ["Source attributes", element.metadataJson?.disciplineSourceAttributes?.join("; ")]])}</div></Card>
    <Card><h2 className="font-semibold">Materials</h2><p className="mt-3 text-sm">{materialStatus === "VIRTUAL_REFERENCE" ? "Virtual material reference" : materialStatus === "MISSING_FROM_SOURCE" || !element.materialSummary ? "Material not defined in source IFC — material data incomplete" : element.materialSummary}</p></Card>
    <Card><h2 className="font-semibold">Element properties</h2><div className="mt-3"><ReadableRows value={element.propertiesJson || {}} units={element.metadataJson?.units}/></div></Card>
    <Card><h2 className="font-semibold">Element quantities</h2><div className="mt-3"><ReadableRows value={element.quantitiesJson || {}} quantities units={element.metadataJson?.units}/></div></Card>
    <Card><h2 className="font-semibold">Relationships</h2><div className="mt-3">{fields([["Contained storey", nodeName(element.storeyNodeId)], ["Contained space", nodeName(element.spaceNodeId)], ["Connected systems", element.systemName], ["Type definition", element.typeName]])}</div></Card>
    <details className="rounded-lg border bg-card p-4"><summary className="cursor-pointer font-semibold">Developer Data</summary><pre className="mt-3 max-h-80 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-200">{JSON.stringify(element, null, 2)}</pre></details>
  </div>;
};

export const ElementsTab = ({ projectId, versionId, nodes, findings, initialElementIds, onFocus3D }: { projectId: string; versionId: string; nodes: IFCSpatialNode[]; findings: IFCFinding[]; initialElementIds?: string[]; onFocus3D?:(id:string)=>void }) => {
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [items, setItems] = useState<IFCElement[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<IFCElement>();
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [linkedIds, setLinkedIds] = useState<string[]>(initialElementIds || []);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const options = useMemo(() => ({ disciplines: Array.from(new Set(items.map((item) => item.discipline).filter(Boolean))), classes: Array.from(new Set(items.map((item) => item.entityType))).sort(), storeys: nodes.filter((node) => node.nodeType === "STOREY") }), [items, nodes]);
  const issueCounts = useMemo(() => { const counts = new Map<string, number>(); findings.forEach((finding) => finding.affectedElementIds.forEach((id) => counts.set(id, (counts.get(id) || 0) + 1))); return counts; }, [findings]);
  useEffect(() => setLinkedIds(initialElementIds || []), [initialElementIds]);
  const visibleItems = useMemo(() => items.filter((item) => {
    const classified = Boolean(item.metadataJson?.classifications?.length);
    const classificationMatch = !filters.classification || (filters.classification === "CLASSIFIED" ? classified : !classified);
    const severityMatch = !filters.issueSeverity || findings.some((finding) => finding.severity === filters.issueSeverity && finding.affectedElementIds.includes(item.id));
    return classificationMatch && severityMatch;
  }), [filters.classification, filters.issueSeverity, findings, items]);

  useEffect(() => {
    const serverFilters = Object.fromEntries(Object.entries(filters).filter(([key]) => !["classification", "issueSeverity"].includes(key)));
    const timer = window.setTimeout(() => { setLoading(true); setError(""); void api.ifc.elements(projectId, versionId, { ...serverFilters, elementIds: linkedIds.join(","), pageSize: 100 }).then((page) => { setItems(page.items); setTotal(page.total); setSelected((current) => page.items.find((item) => item.id === current?.id) || page.items.find((item) => linkedIds.includes(item.id) || linkedIds.includes(item.globalId)) || page.items[0]); }).catch((reason) => { console.error("[IFC Intelligence:Elements] loading failed", reason); setError("Elements could not be loaded. Other model analysis remains available."); }).finally(() => setLoading(false)); }, 250);
    return () => window.clearTimeout(timer);
  }, [filters, linkedIds, projectId, reload, versionId]);

  const patchFilter = (key: keyof Filters, value: string) => setFilters((current) => ({ ...current, [key]: value }));
  const toggle = (id: string) => setChecked((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const exportRows = async () => {
    const serverFilters = Object.fromEntries(Object.entries(filters).filter(([key]) => !["classification", "issueSeverity"].includes(key)));
    const pageCount = Math.ceil(total / 200); const pages = await Promise.all(Array.from({ length: pageCount }, (_, index) => api.ifc.elements(projectId, versionId, { ...serverFilters, elementIds: linkedIds.join(","), page: index + 1, pageSize: 200 })));
    const rows = pages.flatMap((page) => page.items).filter((item) => {
      const classified = Boolean(item.metadataJson?.classifications?.length);
      return (!filters.classification || (filters.classification === "CLASSIFIED" ? classified : !classified)) && (!filters.issueSeverity || findings.some((finding) => finding.severity === filters.issueSeverity && finding.affectedElementIds.includes(item.id)));
    }); const headers = ["Element name", "IFC class", "Element type", "Discipline", "Storey", "Space", "System", "Material", "Tag", "GlobalId", "Classification", "Completeness"];
    const nodeName = (id?: string) => nodes.find((node) => node.id === id)?.name || "";
    const csv = [headers.map(csvCell).join(","), ...rows.map((item) => [item.metadataJson?.originalName || item.name, item.entityType, item.typeName, item.discipline, nodeName(item.storeyNodeId), nodeName(item.spaceNodeId), item.systemName, item.materialSummary, item.tag, item.globalId, classificationLabel(item), item.metadataJson?.completenessStatus].map(csvCell).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "ifc-elements-filtered.csv"; anchor.click(); URL.revokeObjectURL(url);
  };

  return <div className="space-y-4"><Card>{!!linkedIds.length && <div className="mb-3 flex items-center justify-between rounded-lg bg-primary/5 p-3 text-sm"><span>Showing elements linked from a finding or suggestion.</span><Button size="sm" variant="ghost" onClick={() => setLinkedIds([])}>Show all elements</Button></div>}<div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6"><div className="relative xl:col-span-2"><Search className="absolute left-3 top-3 text-muted-foreground" size={16}/><input aria-label="Search elements" className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm" value={filters.q} onChange={(event) => patchFilter("q", event.target.value)} placeholder="Search name, type, tag or GlobalId"/></div><select aria-label="Discipline" className={selectClass} value={filters.discipline} onChange={(event) => patchFilter("discipline", event.target.value)}><option value="">All disciplines</option>{options.disciplines.map((value) => <option key={value} value={value}>{labelize(value)}</option>)}</select><select aria-label="Storey" className={selectClass} value={filters.storeyId} onChange={(event) => patchFilter("storeyId", event.target.value)}><option value="">All storeys</option>{options.storeys.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}</select><select aria-label="IFC class" className={selectClass} value={filters.entityType} onChange={(event) => patchFilter("entityType", event.target.value)}><option value="">All IFC classes</option>{options.classes.map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Completeness" className={selectClass} value={filters.completeness} onChange={(event) => patchFilter("completeness", event.target.value)}><option value="">All completeness</option><option value="COMPLETE">Complete</option><option value="PARTIAL">Partial</option><option value="INCOMPLETE">Incomplete</option></select><input aria-label="Element type filter" className={selectClass} value={filters.elementType} onChange={(event) => patchFilter("elementType", event.target.value)} placeholder="Element type"/><input aria-label="Material filter" className={selectClass} value={filters.material} onChange={(event) => patchFilter("material", event.target.value)} placeholder="Material"/><input aria-label="System filter" className={selectClass} value={filters.system} onChange={(event) => patchFilter("system", event.target.value)} placeholder="System"/><select aria-label="Classification" className={selectClass} value={filters.classification} onChange={(event) => patchFilter("classification", event.target.value)}><option value="">All classifications</option><option value="CLASSIFIED">Classified</option><option value="MISSING">Missing classification</option></select><select aria-label="Issue severity" className={selectClass} value={filters.issueSeverity} onChange={(event) => patchFilter("issueSeverity", event.target.value)}><option value="">All issue severities</option>{["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATION"].map((value) => <option key={value}>{value}</option>)}</select></div><div className="mt-3 flex flex-wrap items-center justify-end gap-3"><div className="flex items-center gap-2 text-sm text-muted-foreground"><span>{visibleItems.length === items.length ? total.toLocaleString() : visibleItems.length.toLocaleString()} elements · {checked.size} selected</span><Button variant="outline" size="sm" disabled={!total} onClick={() => void exportRows()}><Download size={15}/> Export filtered results</Button></div></div></Card>
    {loading ? <LoadingState label="Loading elements…"/> : error ? <ErrorState message={error} onRetry={() => setReload((value) => value + 1)}/> : !visibleItems.length ? <EmptyState title="No elements match these filters" description="Clear or change the filters to view extracted model elements."/> : <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(360px,1fr)]"><Card padding="none"><div className="overflow-auto"><table className="min-w-[1450px] w-full text-left text-sm"><thead className="sticky top-0 bg-muted"><tr><th className="p-3">Select</th>{[["name", "Element name"], ["ifcClass", "IFC class"], ["type", "Element type"], ["discipline", "Discipline"], ["storey", "Storey"], ["space", "Space"], ["system", "System"], ["material", "Material"], ["classification", "Classification"], ["tag", "Tag / GlobalId"], ["issues", "Data / issues"]].map(([key, label]) => <th key={key} className="p-3"><button onClick={() => key !== "issues" && key !== "storey" && key !== "space" && key !== "system" && key !== "material" && key !== "classification" && setFilters((current) => ({ ...current, sortBy: key, sortDirection: current.sortBy === key && current.sortDirection === "asc" ? "desc" : "asc" }))}>{label}</button></th>)}</tr></thead><tbody className="divide-y">{visibleItems.map((item) => <tr key={item.id} className={`cursor-pointer hover:bg-muted/40 ${selected?.id === item.id ? "bg-primary/5" : ""}`} onClick={() => setSelected(item)}><td className="p-3"><button aria-label={`Select ${item.name}`} onClick={(event) => { event.stopPropagation(); toggle(item.id); }}>{checked.has(item.id) ? <CheckSquare size={17}/> : <Square size={17}/>}</button></td><td className="p-3"><b>{item.metadataJson?.originalName || item.name}</b>{!item.metadataJson?.originalName && <small className="block text-muted-foreground">Original IFC name missing</small>}</td><td className="p-3">{item.entityType}</td><td className="p-3">{displayValue(item.typeName)}</td><td className="p-3"><Badge>{labelize(item.discipline)}</Badge></td><td className="p-3">{displayValue(nodes.find((node) => node.id === item.storeyNodeId)?.name)}</td><td className="p-3">{displayValue(nodes.find((node) => node.id === item.spaceNodeId)?.name)}</td><td className="p-3">{displayValue(item.systemName)}</td><td className="p-3">{displayValue(item.materialSummary)}</td><td className="p-3 max-w-52 truncate" title={classificationLabel(item)}>{classificationLabel(item)}</td><td className="p-3"><span>{displayValue(item.tag)}</span><small className="block max-w-32 truncate text-muted-foreground" title={item.globalId}>{item.globalId}</small></td><td className="p-3"><Badge variant={item.metadataJson?.completenessStatus === "COMPLETE" ? "success" : "warning"}>{labelize(item.metadataJson?.completenessStatus)}</Badge><small className="ml-2">{issueCounts.get(item.id) || 0}</small></td></tr>)}</tbody></table></div></Card><ElementDetails element={selected} nodes={nodes} issueCount={selected ? issueCounts.get(selected.id) || 0 : 0} onFocus3D={onFocus3D}/></div>}
  </div>;
};
