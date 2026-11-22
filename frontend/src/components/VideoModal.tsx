import { useState } from "react";
import { Alert, Modal } from "./ui";

export default function VideoModal({ title, url, onClose }: { title: string; url: string; onClose: () => void }) {
  const [error, setError] = useState("");
  return <Modal title={title} onClose={onClose}>
    <video controls autoPlay src={url} onError={() => setError("This browser could not play the file. Try downloading it from the Recordings page.")} />
    {error && <div className="modal-body"><Alert tone="error">{error}</Alert></div>}
  </Modal>;
}
