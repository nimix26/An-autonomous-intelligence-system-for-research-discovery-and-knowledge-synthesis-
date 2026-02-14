const Sidebar = () => {
  return (
    <div className="w-64 bg-gray-900 text-white p-6">
      <ul className="space-y-4">
        <li className="hover:text-blue-400 cursor-pointer">Dashboard</li>
        <li className="hover:text-blue-400 cursor-pointer">Discover</li>
        <li className="hover:text-blue-400 cursor-pointer">Synthesis</li>
        <li className="hover:text-blue-400 cursor-pointer">Knowledge Graph</li>
      </ul>
    </div>
  );
};

export default Sidebar;
