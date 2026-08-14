import { useState } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../../utils/errorMessage";
import { Paperclip, Trash2, Upload } from "lucide-react";
import api from "../../../services/api";
import type { Attachment, AttachmentEntityType } from "../../../types/attachment";
import toast from "react-hot-toast";

export const AttachmentPanel = ({ projectId, entityType, entityId, initialCount = 0, readOnly = false }: {
  projectId: string; entityType: AttachmentEntityType; entityId: string; initialCount?: number; readOnly?: boolean;
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Attachment[]>([]);
  const [count, setCount] = useState(initialCount);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const data = await api.attachments.list({ projectId, entityType, entityId });
      setItems(data); setCount(data.length);
    } catch (err: any) {
      toast.error(errorMessage(err, "Attachments could not be loaded."));
    }
  };
  const toggle = async () => {
    const next = !open; setOpen(next);
    if (next) await load();
  };
  const upload = async (file?: File) => {
    if (!file) return;
    setBusy(true);
    try { await api.attachments.upload(file, projectId, entityType, entityId); await load(); toast.success("Attachment uploaded."); }
    catch (err: any) { toast.error(errorMessage(err, "File upload failed.")); }
    finally { setBusy(false); }
  };

  return <div className="mt-3 border-t pt-3">
    <button type="button" onClick={toggle} className="flex items-center gap-1 text-xs font-medium text-primary hover:underline">
      <Paperclip size={13} /> Attachments ({count})
    </button>
    {open && <div className="mt-3 space-y-2 rounded-lg bg-muted/20 p-3">
      {items.map((item) => <div key={item.id} className="flex items-center gap-2 text-xs">
        <a href={item.fileUrl} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-primary hover:underline">{item.originalFilename}</a>
        <span className="text-muted-foreground">{Math.ceil(item.fileSizeBytes / 1024)} KB</span>
        {!readOnly && <button aria-label={t("attachmentPanel.delete_attachment")} onClick={async () => { try { await api.attachments.delete(item.id); await load(); toast.success("Attachment deleted."); } catch (err: any) { toast.error(errorMessage(err, "Attachment could not be deleted.")); } }}><Trash2 size={13} /></button>}
      </div>)}
      {items.length === 0 && <p className="text-xs text-muted-foreground">{t("attachmentPanel.no_files_attached_to_this_event")}</p>}
      {!readOnly && <label className="inline-flex cursor-pointer items-center gap-2 text-xs font-medium text-primary">
        <Upload size={13} /> {busy ? "Uploading…" : "Add image or PDF"}
        <input type="file" className="hidden" accept=".jpg,.jpeg,.png,.pdf,.doc,.docx,.xls,.xlsx" disabled={busy} onChange={(event) => upload(event.target.files?.[0])} />
      </label>}
    </div>}
  </div>;
};
