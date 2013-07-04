
import socket
import struct
import select

class IncompleteMessageError(Exception): pass
class NotAuthenticatedError(Exception): pass

class Message(object):
	
	SERVERDATA_AUTH = 3
	SERVERDATA_AUTH_RESPONSE = 2
	SERVERDATA_EXECCOMAND = 2
	SERVERDATA_RESPONSE_VALUE = 0
	
	def __init__(self, id, type, body=u""):
		
		self.id = id
		self.type = type
		self.body = body
		
		self.response = None
	
	def __str__(self):
		return "{type} ({id}) '{body}'".format(
					type={
						Message.SERVERDATA_AUTH: "SERVERDATA_AUTH",
						Message.SERVERDATA_AUTH_RESPONSE: "SERVERDATA_AUTH_RESPONSE/SERVERDATA_EXECCOMAND",
						Message.SERVERDATA_RESPONSE_VALUE: "SERVERDATA_RESPONSE_VALUE"
					}.get(self.type, "INVALID"),
					id=self.id,
					body=self.body)
	
	@property
	def size(self):
		"""
			Packet size in bytes, minus the 'size' fields (4 bytes).
		"""
		return struct.calcsize("<ii") + len(self.body.encode("ascii")) + 2
	
	def encode(self):
		return struct.pack("<iii", self.size, self.id, self.type) + \
					self.body.encode("ascii") + "\x00\x00"
	
	@classmethod
	def decode(cls, buffer):
		"""
			Will attempt to decode a single message from a byte buffer,
			returning a corresponding Message instance and the remaining
			buffer contents if any.
		
			If buffer is does not contain at least one full message, 
			IncompleteMessageError is raised.
		"""
		
		if len(buffer) < struct.calcsize("<i"):
			raise IncompleteMessageError
			
		size = struct.unpack("<i", buffer[:4])[0]
		if len(buffer) - struct.calcsize("<i") < size:
			raise IncompleteMessageError
		
		packet = buffer[:size + 4]
		buffer = buffer[size + 4:]
		
		id = struct.unpack("<i", packet[4:8])[0]
		type = struct.unpack("<i", packet[8:12])[0]
		body = packet[12:][:-2].decode("ascii")
		
		return cls(id, type, body), buffer
		
class RCON(object):
	
	def __init__(self, address):
		
		self.host = address[0]
		self.port = address[1]
		
		self._next_id = 1
		self._read_buffer = ""
		self._active_requests = {}
		
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.connect((self.host, self.port))
		
		self.is_authenticated = False
	
	def disconnect(self):
		self.socket.close()
	
	def request(self, type, body=u""):
		
		request = Message(self._next_id, type, body)
		self._active_requests[request.id] = request
		self._next_id += 1
		
		self.socket.send(request.encode())
		return request
	
	def process(self):
		
		ready = select.select([self.socket], [], [], 2.0)
		if ready:
			self._read_buffer += self.socket.recv(4096)
		
		response, self._read_buffer = Message.decode(self._read_buffer)
		self._active_requests[response.id].response = response
	
	def response_to(self, request, timeout=10.0):
		"""
			Returns a context manager that waits up to a given time for
			a response to a specific request. Assumes the request has
			actually been sent to an RCON server.
		"""
		
		class ResponseContextManager(object):
			
			def __init__(self, rcon, request):
				
				self.rcon = rcon
				self.request = request
			
			def __enter__(self):
				
				while self.request.response is None:
					try:
						self.rcon.process()
					except IncompleteMessageError:
						pass
					
				return self.request.response
			
			def __exit__(self, type, value, tb):
				pass
			
		return ResponseContextManager(self, request)
		
	def authenticate(self, password):
		
		request = self.request(Message.SERVERDATA_AUTH, unicode(password))
		with self.response_to(request) as response:
			print response
			self.is_authenticated = True
		
	def execute(self, command):
		
		request = self.request(Message.SERVERDATA_EXECCOMAND, unicode(command))
		return request
		

def shell(rcon=None):
	
	def prompt(prompt=None):
		if prompt:
			return raw_input("{}: ".format(prompt))
		else:
			return raw_input("{}:{}>".format(rcon.host, rcon.port))
	
	if rcon is None:
		rcon = RCON((prompt("host"), int(prompt("port"))))

	if not rcon.is_authenticated:
		rcon.authenticate(prompt("password"))
		
	while True:
		cmd = rcon.execute(prompt())
		with rcon.response_to(cmd) as response:
			print response.body
		