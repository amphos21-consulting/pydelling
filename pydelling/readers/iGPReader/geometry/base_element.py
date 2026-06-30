"""
Module documentation.


"""

from pydelling.config import config


class BaseElement:
    """Base iGP mesh element storing connectivity, coordinates, and faces.

    Category: iGP geometry.
    Tags: element, mesh, nodes, faces, centroid.
    Use when: an MCP agent needs the common attributes shared by iGP element
        types before export or region operations.
    """

    def __init__(self, node_ids, node_coords, element_type_n, local_id, centroid_coords=None):
        """Create a base mesh element from node ids and coordinates.

        Category: iGP geometry.
        Tags: element, nodes, coordinates, centroid, faces.
        Use when: constructing element subclasses that share connectivity and
            face-storage behavior.
        Args:
            node_ids: Node ids defining the element connectivity.
            node_coords: Coordinates for each node.
            element_type_n: Number of nodes for this element type.
            local_id: Element id in the local mesh.
            centroid_coords: Optional precomputed centroid coordinates.
        Side effects:
            Stores connectivity, coordinates, type metadata, local id, and an
            empty face dictionary.
        """
        self.nodes = node_ids  # Node id set
        self.coords = node_coords  # Coordinates of each node
        self.centroid_coords = centroid_coords
        self.type = 'BaseElement'
        self.n_type = element_type_n  # Number of node_ids for an element
        self.local_id = local_id  # Element id
        self.faces = {}  # Dictionary to store face information

    def __repr__(self):
        # print("### Element info ###")
        # print(f"Element ID: {self.local_id}")
        # print(f"Number of nodes: {self.n_type}")
        # print(f"Element type: {self.type}")
        # print(f"Node list: {self.nodes}")
        # print("### End element info ###")
        #
        # print("### Face info ###")
        # for face in self.faces:
        #     print(f"{face}: {self.faces[face].coords}")
        # print("### End face info ###")
        return f"{self.type} {self.local_id}"


    def print_element_info(self):
        """Print element connectivity and type metadata.

        Category: iGP geometry.
        Tags: element, debug, connectivity.
        Use when: interactively inspecting an iGP element during debugging.
        Side effects:
            Writes element information to stdout.
        """
        print("### Element info ###")
        print(f"Element ID: {self.local_id}")
        print(f"Number of nodes: {self.n_type}")
        print(f"Element type: {self.type}")
        print(f"Node list: {self.nodes}")
        print("### End element info ###")

    def print_face_info(self):
        """Print stored face coordinate information.

        Category: iGP geometry.
        Tags: element, faces, debug.
        Use when: interactively inspecting face geometry attached to an iGP
            element.
        Side effects:
            Writes face information to stdout.
        """
        print("### Face info ###")
        for face in self.faces:
            print(f"{face}: {self.faces[face].coords}")
        print("### End face info ###")
