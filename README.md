# Distributed P2P File Sharing System
We implemented this project as a course project for the distributed systems class at the University of Tehran.  
The project aims to send files with any extension on a network of devices connected using __Wi-Fi__ and __Bluetooth__. Moreover, the project can distribute the files using __chunked__ data structures in a __fault-tolerant__ manner using write-ahead logging (WAL).
# Architecture
## Network Messages
Various network message types are defined to let us achieve different functionalities. The following list states the message types alongside their definitions:
- __File Transfer__: Packets transfering the actual file use this message type.
- __Join__: This message is used when a new node is connected to the network either via Bluetooth or Wi-Fi.
- __File Search__: This message is used for finding a file in the network. The nodes containing the requested file send back a __Has File__ Message after receiving this message.
- __Has File__: The nodes storing a requested file send this message type to show the availability of the requested file.
- __Transfer Request__: The requester send this message type after receiving the __Has File__ message.
- __ACK__: The requester acknowledges received file chunks using this message type. __ACK__ message type is further used to achieve fault tolerance.
## Fault-Tolerance Mechanism
We used a write-ahead log (WAL) to achieve fault tolerance over the network. The sender nodes always write to the WAL before sending the requested files, and after receiving all ACK messages for sent chunks, the sender removes the entry from its WAL. Using the mentioned approach, we implemented two fault tolerance mechanisms:
### Sender Failure
When the sender fails in the middle of sending a file, the WAL entries are not removed since the sender does not notice ACK messages after the failure. We implemented a mechanism for all nodes to analyze the WAL on startup to notice any remaining entries. Using this technique, the sender node can identify the failure and retransmit the requested chunks.
### Requester or Middle Node Failure
We developed a failure detection mechanism in scenarios where the requester node or middle nodes fail for a short time. WAL stores the time of the last ACK received, and every sender node has a particular thread for checking the time passed from this stored moment. Therefore, if a specific duration (20 seconds in the implemented protocol) passes without ACK messages, the sender retransmits the chunks. This method allows for handling scenarios where a receiver or middle node goes down for some time and returns online.
## Routing
Each node in the network stores a routing table of its direct neighbors, further used for routing purposes. The initial tables are empty, but they get filled with the information of the transferred packets over time.
# Usage
## Node Startup
```
python3 node.py
```
## Commands Available
- __join [node_address]__: join another node in the network with either Bluetooth or Wi-Fi.
- __request [filename]__: request a file from the nodes participating in the network.
- __leave__: leave the network.
- __help__: observe the available commands.
