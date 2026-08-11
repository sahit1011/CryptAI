import { redirect } from "next/navigation";

/** /terminal — renamed to /chart. Kept so existing links and bookmarks still land. */
export default function TerminalPage() {
    redirect("/chart");
}
