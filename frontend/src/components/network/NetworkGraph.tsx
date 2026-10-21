import React, { useEffect, useRef } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import { Info, MapPin, Building, Phone, User, Car } from 'lucide-react';

interface NetworkGraphProps {
  nodes: any[];
  edges: any[];
  onSelectNode: (nodeId: string) => void;
  selectedFilter: string;
}

export const NetworkGraph: React.FC<NetworkGraphProps> = ({
  nodes,
  edges,
  onSelectNode,
  selectedFilter,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);

  // Filter nodes if selected
  const filteredNodes =
    selectedFilter === 'ALL'
      ? nodes
      : nodes.filter((n) => {
          if (selectedFilter === 'PHONE') {
            return n.entity_type === 'PHONE' || n.entity_type === 'PHONE_NUMBER';
          }
          return n.entity_type === selectedFilter;
        });

  const validNodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter(
    (e) => validNodeIds.has(e.from) && validNodeIds.has(e.to)
  );

  useEffect(() => {
    if (!containerRef.current || filteredNodes.length === 0) return;

    const data = {
      nodes: new DataSet(filteredNodes),
      edges: new DataSet(filteredEdges),
    };

    const options = {
      nodes: {
        shape: 'dot',
        font: {
          size: 13,
          color: '#1e293b',
          face: 'Inter, sans-serif',
        },
        borderWidth: 2,
        shadow: true,
      },
      edges: {
        width: 1.5,
        color: { color: '#94a3b8', highlight: '#2563eb' },
        smooth: {
          type: 'continuous',
        },
        font: {
          size: 10,
          align: 'middle',
        },
      },
      physics: {
        stabilization: true,
        barnesHut: {
          gravitationalConstant: -3500,
          springConstant: 0.04,
          springLength: 95,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        zoomView: true,
      },
    };

    const network = new Network(containerRef.current, data as any, options as any);
    networkRef.current = network;

    network.on('click', (params) => {
      if (params.nodes.length > 0) {
        onSelectNode(params.nodes[0]);
      }
    });

    return () => {
      network.destroy();
    };
  }, [nodes, edges, selectedFilter, onSelectNode, filteredNodes.length]);

  if (filteredNodes.length === 0) {
    const getIcon = () => {
      if (selectedFilter === 'LOCATION') return <MapPin className="w-8 h-8 text-emerald-600" />;
      if (selectedFilter === 'ORGANIZATION') return <Building className="w-8 h-8 text-purple-600" />;
      if (selectedFilter === 'PHONE') return <Phone className="w-8 h-8 text-cyan-600" />;
      if (selectedFilter === 'VEHICLE') return <Car className="w-8 h-8 text-amber-600" />;
      if (selectedFilter === 'PERSON') return <User className="w-8 h-8 text-blue-600" />;
      return <Info className="w-8 h-8 text-slate-400" />;
    };

    return (
      <div className="w-full h-full bg-slate-50 border border-slate-200 rounded-xl flex flex-col items-center justify-center p-6 text-center animate-in fade-in duration-150">
        <div className="p-3 bg-white rounded-full shadow-xs border border-slate-200 mb-3">
          {getIcon()}
        </div>
        <h4 className="text-sm font-bold text-slate-800">
          No {selectedFilter === 'ALL' ? 'Entity' : selectedFilter === 'PHONE' ? 'Phone Number' : selectedFilter} Records Found
        </h4>
        <p className="text-xs text-slate-500 max-w-sm mt-1">
          {selectedFilter === 'LOCATION'
            ? 'No location entities or places of occurrence have been registered or extracted for this scope.'
            : selectedFilter === 'ORGANIZATION'
            ? 'No commercial, syndicate, or organizational entities are linked to the selected FIR case scope.'
            : selectedFilter === 'PHONE'
            ? 'No contact or suspect phone numbers have been extracted or linked in the selected scope.'
            : 'No matching entity records are available for the current filter criteria.'}
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full h-full bg-slate-50 border border-slate-200 rounded-xl"
    />
  );
};
