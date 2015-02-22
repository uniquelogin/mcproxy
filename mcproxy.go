package main

import "net"
import "fmt"
import "log"
import "time"
import "os"
import "flag"


func tickerLoop(c chan int) {
    for {
        time.Sleep(5 * time.Second)
        c <- 0
    }
}

func readLoop(conn *net.TCPConn, c chan []byte) {
    for {
        buf := make([]byte, 65536)
        numread, err := conn.Read(buf)
        if err != nil {
            c <- buf[:0]
            break
        }
        c <- buf[:numread]
    }
}

func handleConn(clientConn *net.TCPConn, serverAddr string) {
    serverLogName := fmt.Sprintf("log_%d", time.Now().Unix())
    logFile, err := os.Create(serverLogName)
    if err != nil {
        panic(fmt.Sprintf("Failed to open output log file %s", serverLogName))
    }

    addr, err := net.ResolveTCPAddr("tcp4", serverAddr)
    if err != nil {
        panic("IPv4 is no longer supported, it seems")
    }
    serverConn, err := net.DialTCP("tcp4", nil, addr)
    log.Print("Connected to the remote MC server")
    clientConn.SetNoDelay(true)
    serverConn.SetNoDelay(true)
    clientChan := make(chan []byte)
    serverChan := make(chan []byte)
    statsChan := make(chan int)
    go readLoop(clientConn, clientChan)
    go readLoop(serverConn, serverChan)
    go tickerLoop(statsChan)
    fromServer := 0
    fromClient := 0
    terminate := false;
    for !terminate {
        select {
        case buf := <-clientChan:
            if len(buf) == 0 {
                log.Print("Client closed the connection")
                terminate = true
            } else {
                fromClient += len(buf)
                serverConn.Write(buf)
            }
        case buf := <-serverChan:
            if len(buf) == 0 {
                log.Print("Server closed the connection")
                terminate = true
            } else {
                fromServer += len(buf)
                clientConn.Write(buf)
                logFile.Write(buf)
            }
        case <-statsChan:
            log.Print(fmt.Sprintf("Stats: %d kbytes from server, %d kbytes from client", fromServer/1024, fromClient/1024))
        }
    }
    logFile.Close()
    serverConn.Close()
    clientConn.Close()
}

func getCmd () (proxyAddrPtr, serverAddrPtr  *string) {
	proxyAddrPtr = flag.String("proxy_addr", "localhost:25565", "MC proxy address")
	serverAddrPtr = flag.String("server_addr", "localhost:25566", "MC server address")
	flag.Parse()

	return proxyAddrPtr, serverAddrPtr
}

func main() {
    var proxyAddrPtr, serverAddrPtr *string	= getCmd()

    addr, err := net.ResolveTCPAddr("tcp4", *proxyAddrPtr)
    if err != nil {
		panic(fmt.Sprintf(" Failed to understand %v, duh", *proxyAddrPtr))
    }

    l, err := net.ListenTCP("tcp4", addr)
    if err != nil {
        panic(fmt.Sprintf("Failed to listen on %v", *proxyAddrPtr))
    }

    log.Print("Listening");

    for { 
        conn, err := l.AcceptTCP()
        if err != nil {
            fmt.Println("Error accepting the inbound connection")
        } else {
            log.Print("Accepted a connection")
            go handleConn(conn, *serverAddrPtr)
        }
    }
}
