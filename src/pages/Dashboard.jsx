import React from "react";

export default function ResearchDashboard() {
  return (
    <div className="min-h-screen bg-gray-950 text-white flex">
      
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 p-6 border-r border-gray-800 hidden md:block">
        <h1 className="text-2xl font-bold text-indigo-400 mb-8">
          ResearchAI
        </h1>

        <nav className="space-y-4 text-gray-300">
          <div className="hover:text-indigo-400 cursor-pointer">Dashboard</div>
          <div className="hover:text-indigo-400 cursor-pointer">Saved Papers</div>
          <div className="hover:text-indigo-400 cursor-pointer">Knowledge Graph</div>
          <div className="hover:text-indigo-400 cursor-pointer">Settings</div>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-6 md:p-10">

        {/* Top Search Bar */}
        <div className="max-w-4xl mx-auto mb-10">
          <h2 className="text-3xl font-semibold mb-6 text-center">
            Discover & Synthesize Research
          </h2>

          <div className="flex shadow-lg rounded-xl overflow-hidden border border-gray-800">
            <input
              type="text"
              placeholder="Enter research topic (e.g., Autonomous Agents in AI)..."
              className="flex-1 p-4 bg-gray-900 focus:outline-none text-white"
            />
            <button className="bg-indigo-600 hover:bg-indigo-700 px-6">
              Analyze
            </button>
          </div>
        </div>

        {/* Results Section */}
        <section className="max-w-6xl mx-auto grid md:grid-cols-2 gap-6">
          
          {/* Paper Card */}
          <div className="bg-gray-900 p-6 rounded-xl border border-gray-800 hover:border-indigo-500 transition">
            <h3 className="text-lg font-semibold mb-2">
              Autonomous Multi-Agent Research Systems
            </h3>
            <p className="text-gray-400 text-sm mb-4">
              Summary: This paper explores intelligent agent collaboration in research discovery...
            </p>
            <div className="flex justify-between text-xs text-gray-500">
              <span>Year: 2025</span>
              <span>Citations: 124</span>
            </div>
          </div>

          {/* Paper Card */}
          <div className="bg-gray-900 p-6 rounded-xl border border-gray-800 hover:border-indigo-500 transition">
            <h3 className="text-lg font-semibold mb-2">
              Knowledge Graphs for Scientific Synthesis
            </h3>
            <p className="text-gray-400 text-sm mb-4">
              Summary: Integration of structured knowledge graphs to enhance automated reasoning...
            </p>
            <div className="flex justify-between text-xs text-gray-500">
              <span>Year: 2024</span>
              <span>Citations: 89</span>
            </div>
          </div>

        </section>
      </main>
    </div>
  );
}