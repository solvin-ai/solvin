// pages/index.js

import Link from "next/link";

export default function MainMenu() {
return (
<div className="min-h-screen bg-gray-100 flex flex-col items-center justify-center px-4">
<h1 className="text-5xl font-bold mb-8">Main Menu</h1>
<nav className="space-y-6">
<Link href="/settings" className="block text-3xl text-blue-500 hover:underline">
Settings
</Link>
<Link href="/logs" className="block text-3xl text-blue-500 hover:underline">
Logs
</Link>
</nav>
</div>
);
}
