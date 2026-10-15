import React, { useEffect, useRef } from 'react';
import { Network, DataSet } from 'vis-network/standalone';

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

  useEffect(() => {
    if (!containerRef.current) return;

    // Filter nodes if selected
    const filteredNodes =
      selectedFilter === 'ALL'
        ? nodes
        : nodes.filter((n) => n.entity_type === selectedFilter);

    const validNodeIds = new Set(filteredNodes.map((n) => n.id));
    const filteredEdges = edges.filter(
      (e) => validNodeIds.has(e.from) && validNodeIds.has(e.to)
    );

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
  }, [nodes, edges, selectedFilter, onSelectNode]);

  return (
    <div
      ref={containerRef}
      className="w-full h-full bg-slate-50 border border-slate-200 rounded-xl"
    />
  );
};
