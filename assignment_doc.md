Assignment II

•	Assignment Objective  
The assignment aims to develop a “chat room” which is useful for software project team members to exchange text messages / comments, notes, etc.   

•	Problem Statement  
Implement 3-node distributed system which implements the “Chat Room” distributed application.  
Following are the requirements:  
1.	The text messages / comments / notes etc., should be implemented as a single shared file stored in one of the three nodes. This node is termed as a server and maintains shared file as a resource. The remaining two user nodes will run the distributed application code and middleware that will access the file on the server. The middleware is a distributed mutual exclusion software using which the user nodes control the shared file access.  
2.	The distributed application should support a simple text-based UI that runs two shell commands : view and post.  
	`a.	view : This command pulls the existing set of comments / notes from the file server resource and displays on user terminal.`  
	`b.	post<text> : This command takes the text input from the user and posts it to the file server that appends the text to the shared file.`
3.	You can implement view and post commands using two API's on file server or using RPC. There is no need to have authentication. The server side should respond to any user's view and post commands by reading or updating the shared file.  
4.	User can view at any time and multiple users can view at the same time.  
5.	Only one user can get write access (i.e. can post) to the shared file at any point in time. This requires nodes to run a distributed mutual exclusion protocol among themselves.  
6.	Each post command will append the text to the file on the server. We will go by this simple semantic as the basic requirement. So there are no threaded replies or ordering requirement among messages in this collaboration application.  
7.	A post should also record the time the post was called from user node (not the server time when it was received), user/node id along with the text comment / note.  

Sample shared file content:  
12 Oct 9:01AM Lucy: Welcome to the team project  
12 Oct 9:04AM Joel: Thanks Lucy - hope to work together  
12 Oct 9:05AM Jina: Joel, will send you all the project outline by eod for comments  
…  

Here's a sample CLI based experience for user Joel:  
Joel_machine> view  
12 Oct 9:01AM Lucy: Welcome to the team project  
Joel_machine> post “Thanks Lucy - hope to work together”  
Joel_machine> view  
12 Oct 9:01AM Lucy: Welcome to the team project  
12 Oct 9:04AM Joel: Thanks Lucy - hope to work together  
12 Oct 9:05AM Jina: Joel, will send you all the project outline by eod for comments  

Important Note:  
1.	Keep the following 2 pieces in separate code modules: (a) DME algorithm (the distributed middleware) and (b) collaboration application (the user application) that calls the DME algorithm as and when required. You can use Lamport’s or any other DME algorithm of your choice. But do not use a trivial centralised solution.  
2.	Create appropriate logs in your system to verify and demonstrate that actually DME algorithm is working controlling user access to the resource.  

•	Platform:  
Assignment should be carried out in group (Groups are already created and available in Taxila) and should be implemented on Cloud based lab using 3 nodes available. Assignment should be implemented using C Programming Language (Recommended).  Groups may alternatively use Java or Python for the implementation.