// pages/api/github/repos.js

import fetch from "node-fetch";

export default async function handler(req, res) {
  const API_URL_GITHUB = process.env.API_URL_GITHUB || "https://api.github.com";
  const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
  if (!GITHUB_TOKEN) {
    return res.status(500).json({ error: "GITHUB_TOKEN environment variable is not set." });
  }

  const headers = {
    "Authorization": `token ${GITHUB_TOKEN}`,
    "Accept": "application/vnd.github+json"
  };

  try {
    // 1) Fetch organizations for the authenticated user
    let orgs = [];
    let page = 1;
    while (true) {
      const orgsUrl = `${API_URL_GITHUB}/user/orgs?per_page=100&page=${page}`;
      const orgRes = await fetch(orgsUrl, { headers });
      if (!orgRes.ok) {
        throw new Error(`Failed fetching orgs: ${orgRes.status}`);
      }
      const orgData = await orgRes.json();
      if (!Array.isArray(orgData) || orgData.length === 0) break;
      orgData.forEach((org) => {
        if (org.login) {
          orgs.push(org.login);
        }
      });
      page++;
    }

    // 2) For each organization, fetch repositories and extract essential info.
    let repositories = [];
    for (const org of orgs) {
      page = 1;
      while (true) {
        const reposUrl = `${API_URL_GITHUB}/orgs/${org}/repos?per_page=100&page=${page}`;
        const reposRes = await fetch(reposUrl, { headers });
        if (!reposRes.ok) {
          throw new Error(`Failed fetching repos for org ${org}: ${reposRes.status}`);
        }
        const reposData = await reposRes.json();
        if (!Array.isArray(reposData) || reposData.length === 0) break;
        reposData.forEach((repo) => {
          repositories.push({
            organization: org,
            name: repo.name,
            clone_url: repo.clone_url
          });
        });
        page++;
      }
    }

    return res.status(200).json({ repositories, total: repositories.length });
  } catch (error) {
    console.error("Error fetching repositories:", error);
    return res.status(500).json({ error: error.message });
  }
}

// pages/settings/repos.js
import { useState, useEffect } from "react";
import Header from "../../components/Header";

export default function ReposPage() {
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchRepos = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/github/repos");
      const data = await res.json();
      if (res.ok) {
        setRepos(data.repositories || []);
      } else {
        setError(data.error || "Error fetching repositories");
      }
    } catch (err) {
      setError("Error fetching repositories");
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchRepos();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Manage Repositories"
        breadcrumbs={[
          { href: "/", label: "Home" },
          { href: "/settings", label: "Settings" },
          { href: "/settings/repos", label: "Repositories" }
        ]}
      />
      <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-gray-800">Repositories</h2>
          <button
            onClick={fetchRepos}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition"
          >
            Refresh
          </button>
        </div>
        {loading && <p>Loading...</p>}
        {error && <p className="text-red-500">{error}</p>}
        {!loading && repos.length === 0 && <p>No repositories found.</p>}
        {repos.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Organization
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Repository
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Clone URL
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {repos.map((repo, index) => (
                  <tr key={index}>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-900">
                      {repo.organization}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-900">
                      {repo.name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-blue-600 hover:underline">
                      <a href={repo.clone_url} target="_blank" rel="noopener noreferrer">
                        {repo.clone_url}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-sm text-gray-600">
              A total of {repos.length} repositories found.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
