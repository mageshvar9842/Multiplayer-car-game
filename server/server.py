import socket
import threading
import json
import time
import random
import string

TCP_PORT = 50000
DISCOVERY_PORT = 50001

def room_code():
    return ''.join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))

class RoomServer:
    def __init__(self):
        self.code = room_code()
        self.clients = {}  # conn -> {"id": str, "x": int, "y": int, "score": int, "lives": int}
        self.obstacles = []  # [{"id": str, "x": int, "y": int, "width": int, "height": int, "speed": int, "type": str}]
        self.running = True
        self.game_active = True
        self.game_start_time = time.time()
        self.game_duration = 60  # 60 seconds game
        self.last_obstacle_spawn = time.time()
        self.obstacle_spawn_interval = 1.5  # spawn every 1.5 seconds
        self.next_obstacle_id = 1

    def start(self):
        print(f"[SERVER] Room created. Code: {self.code}")
        threading.Thread(target=self.discovery_loop, daemon=True).start()
        threading.Thread(target=self.tcp_loop, daemon=True).start()
        self.game_loop()

    # UDP discovery
    def discovery_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", DISCOVERY_PORT))

        while self.running:
            try:
                msg, addr = sock.recvfrom(1024)
                if msg.decode() == "DISCOVER_ROOM":
                    reply = {
                        "type": "room",
                        "room_code": self.code,
                        "host": socket.gethostbyname(socket.gethostname()),
                        "tcp_port": TCP_PORT,
                    }
                    sock.sendto(json.dumps(reply).encode(), addr)
            except:
                pass

    # TCP accept
    def tcp_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("", TCP_PORT))
        srv.listen(8)

        while self.running:
            conn, addr = srv.accept()
            pid = f"P{len(self.clients)+1}"
            self.clients[conn] = {
                "id": pid, 
                "x": 480, 
                "y": 600, 
                "score": 0, 
                "lives": 3,
                "width": 40,
                "height": 40
            }

            welcome_msg = {
                "type": "welcome", 
                "id": pid,
                "game_duration": self.game_duration
            }
            conn.sendall((json.dumps(welcome_msg) + "\n").encode())
            threading.Thread(target=self.client_receiver, args=(conn,), daemon=True).start()

    # TCP receive loop
    def client_receiver(self, conn):
        buf = b""
        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line.decode())

                    # update player position with boundaries
                    player = self.clients[conn]
                    new_x = player["x"] + msg.get("dx", 0)
                    new_y = player["y"] + msg.get("dy", 0)
                    
                    # Keep player in bounds
                    player["x"] = max(0, min(960, new_x))
                    player["y"] = max(0, min(660, new_y))

            except:
                break

        if conn in self.clients:
            del self.clients[conn]
        conn.close()

    def spawn_obstacle(self):
        """Server spawns obstacles"""
        obstacle_types = ["normal", "fast", "bonus", "penalty"]
        obs_type = random.choice(obstacle_types)
        
        # Random x position across screen width
        x = random.randint(50, 900)
        
        obstacle = {
            "id": f"OBS{self.next_obstacle_id}",
            "x": x,
            "y": -60,  # Start above screen
            "width": 50,
            "height": 50,
            "type": obs_type,
            "speed": 3 if obs_type != "fast" else 5,
            "points": 10 if obs_type == "bonus" else (-5 if obs_type == "penalty" else 0)
        }
        
        self.obstacles.append(obstacle)
        self.next_obstacle_id += 1

    def update_obstacles(self):
        """Server updates obstacle movement"""
        for obstacle in self.obstacles[:]:
            obstacle["y"] += obstacle["speed"]
            
            # Remove obstacles that went off screen
            if obstacle["y"] > 750:
                self.obstacles.remove(obstacle)

    def check_collisions(self):
        """Server-side collision detection"""
        for conn, player in list(self.clients.items()):
            if player["lives"] <= 0:
                continue
                
            px, py = player["x"], player["y"]
            pw, ph = player["width"], player["height"]
            
            for obstacle in self.obstacles[:]:
                ox, oy = obstacle["x"], obstacle["y"]
                ow, oh = obstacle["width"], obstacle["height"]
                
                # AABB collision detection
                if (px < ox + ow and px + pw > ox and
                    py < oy + oh and py + ph > oy):
                    
                    # Handle collision based on obstacle type
                    if obstacle["type"] == "bonus":
                        player["score"] += obstacle["points"]
                        print(f"[COLLISION] {player['id']} collected bonus! Score: {player['score']}")
                    elif obstacle["type"] == "penalty":
                        player["score"] += obstacle["points"]  # negative points
                        print(f"[COLLISION] {player['id']} hit penalty! Score: {player['score']}")
                    else:
                        player["lives"] -= 1
                        player["score"] = max(0, player["score"] - 5)
                        print(f"[COLLISION] {player['id']} hit obstacle! Lives: {player['lives']}")
                    
                    # Remove obstacle after collision
                    self.obstacles.remove(obstacle)
                    break

    def check_game_end(self):
        """Game end logic"""
        elapsed = time.time() - self.game_start_time
        
        # Time-based end
        if elapsed >= self.game_duration:
            self.game_active = False
            return True
        
        # All players dead
        if self.clients:
            all_dead = all(p["lives"] <= 0 for p in self.clients.values())
            if all_dead:
                self.game_active = False
                return True
        
        return False

    # Broadcast loop
    def game_loop(self):
        while self.running:
            current_time = time.time()
            
            # Spawn obstacles periodically
            if self.game_active and current_time - self.last_obstacle_spawn > self.obstacle_spawn_interval:
                self.spawn_obstacle()
                self.last_obstacle_spawn = current_time
            
            # Update obstacle positions
            if self.game_active:
                self.update_obstacles()
                self.check_collisions()
            
            # Check for game end
            game_ended = self.check_game_end()
            
            # Calculate time remaining
            time_remaining = max(0, self.game_duration - (current_time - self.game_start_time))
            
            # Prepare state message
            state = {
                "type": "state",
                "players": list(self.clients.values()),
                "obstacles": self.obstacles,
                "game_active": self.game_active,
                "time_remaining": time_remaining,
                "game_ended": game_ended
            }
            
            if game_ended:
                # Add winner info
                if self.clients:
                    winner = max(self.clients.values(), key=lambda p: p["score"])
                    state["winner"] = winner["id"]
                    state["winner_score"] = winner["score"]
            
            data = json.dumps(state).encode() + b"\n"

            # Broadcast to all clients
            for conn in list(self.clients.keys()):
                try:
                    conn.sendall(data)
                except:
                    if conn in self.clients:
                        del self.clients[conn]
                    conn.close()

            time.sleep(1/30)  # 30 ticks per second

if __name__ == "__main__":
    RoomServer().start()
