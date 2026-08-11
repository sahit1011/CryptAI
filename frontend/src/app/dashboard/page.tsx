import { redirect } from "next/navigation";

/**
 * /dashboard — kept as a permanent redirect to the Desk.
 *
 * The app moved from ?section= on this one page to real routes. This stays so old
 * bookmarks, the post-login redirect, and anything still linking here keep landing
 * somewhere sensible instead of 404ing.
 */
export default function DashboardPage() {
    redirect("/desk");
}
