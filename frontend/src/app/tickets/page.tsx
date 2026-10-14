"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api";
import {
  MessageSquare,
  AlertCircle,
  Plus,
  Send,
  CheckCircle2,
  RefreshCw,
  Search,
  Loader2,
  ShieldAlert,
  ArrowRight,
  Inbox,
} from "lucide-react";
import type {
  CurrentUserResponse,
  Ticket,
  TicketPriority,
  TicketStatus,
  Message,
  Conversation,
} from "@/types/api";

export default function TicketsPage() {
  const [currentUser, setCurrentUser] = useState<CurrentUserResponse | null>(null);
  const [activeOrgId, setActiveOrgId] = useState<string | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

  // Tickets state
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [totalTickets, setTotalTickets] = useState(0);
  const [loadingTickets, setLoadingTickets] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterPriority, setFilterPriority] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Detail / Thread view state
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sendingReply, setSendingReply] = useState(false);

  // Create modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newSubject, setNewSubject] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newPriority, setNewPriority] = useState<TicketPriority>("medium");
  const [creatingTicket, setCreatingTicket] = useState(false);

  // 1. Check user authentication
  useEffect(() => {
    async function loadUser() {
      try {
        const user = await apiClient.getCurrentUser();
        setCurrentUser(user);
        if (user.organizations && user.organizations.length > 0 && user.organizations[0]) {
          setActiveOrgId(user.organizations[0].organization_id);
        }
      } catch {
        setCurrentUser(null);
      } finally {
        setAuthChecking(false);
      }
    }
    loadUser();
  }, []);

  // 2. Load tickets when active org changes
  const fetchTickets = useCallback(async () => {
    if (!activeOrgId) return;
    setLoadingTickets(true);
    setErrorMessage(null);
    try {
      const res = await apiClient.listTickets(activeOrgId, {
        status: filterStatus || undefined,
        priority: filterPriority || undefined,
        search: searchQuery.trim() || undefined,
        limit: 50,
      });
      setTickets(res.items);
      setTotalTickets(res.total);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Failed to load tickets.");
      }
    } finally {
      setLoadingTickets(false);
    }
  }, [activeOrgId, filterStatus, filterPriority, searchQuery]);

  useEffect(() => {
    if (activeOrgId) {
      fetchTickets();
    }
  }, [activeOrgId, fetchTickets]);

  // 3. Load conversation & messages for selected ticket
  const openTicketDetail = async (ticket: Ticket) => {
    if (!activeOrgId) return;
    setSelectedTicket(ticket);
    setLoadingMessages(true);
    try {
      const convRes = await apiClient.listTicketConversations(activeOrgId, ticket.id);
      setConversations(convRes.items);
      if (convRes.items.length > 0 && convRes.items[0]) {
        const primaryConv = convRes.items[0];
        const msgRes = await apiClient.listMessages(activeOrgId, primaryConv.id);
        setMessages(msgRes.items);
      } else {
        setMessages([]);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      }
    } finally {
      setLoadingMessages(false);
    }
  };

  // 4. Create Ticket
  const handleCreateTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOrgId || !newSubject.trim()) return;

    setCreatingTicket(true);
    try {
      await apiClient.createTicket(activeOrgId, {
        subject: newSubject.trim(),
        description: newDescription.trim() || undefined,
        priority: newPriority,
        channel: "web",
      });
      setShowCreateModal(false);
      setNewSubject("");
      setNewDescription("");
      setNewPriority("medium");
      await fetchTickets();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      }
    } finally {
      setCreatingTicket(false);
    }
  };

  // 5. Post Message Reply
  const handleSendReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOrgId || !selectedTicket || !replyText.trim() || !conversations[0]) return;

    setSendingReply(true);
    const convId = conversations[0].id;
    try {
      const newMsg = await apiClient.createMessage(activeOrgId, convId, {
        body_text: replyText.trim(),
        author_type: "agent",
        direction: "outbound",
      });
      setMessages((prev) => [...prev, newMsg]);
      setReplyText("");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      }
    } finally {
      setSendingReply(false);
    }
  };

  // 6. Update Status or Priority
  const handleUpdateTicket = async (newStatus?: TicketStatus, newPriority?: TicketPriority) => {
    if (!activeOrgId || !selectedTicket) return;
    try {
      const updated = await apiClient.updateTicket(activeOrgId, selectedTicket.id, {
        status: newStatus,
        priority: newPriority,
        lock_version: selectedTicket.lock_version,
      });
      setSelectedTicket(updated);
      setTickets((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      }
    }
  };

  if (authChecking) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mr-3" />
        <span>Verifying authentication context...</span>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mb-6">
          <ShieldAlert className="w-8 h-8 text-amber-400" />
        </div>
        <h1 className="text-2xl font-bold text-slate-100 mb-2">Authentication Required</h1>
        <p className="text-slate-400 max-w-md mb-6">
          Access to organization tickets and support operations requires an active authenticated session.
        </p>
        <Link
          href="/login"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition shadow-lg shadow-indigo-600/20"
        >
          <span>Sign In to Your Account</span>
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  const activeOrg = currentUser.organizations?.find((o) => o.organization_id === activeOrgId);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Bar */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm font-semibold tracking-wider uppercase text-indigo-400">
            SupportGPT AI
          </Link>
          <span className="text-slate-600">/</span>
          <span className="font-medium text-slate-200">Ticket Operations</span>
          {activeOrg && (
            <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
              {activeOrg.name} ({activeOrg.role})
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchTickets()}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            title="Refresh tickets"
          >
            <RefreshCw className={`w-4 h-4 ${loadingTickets ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition shadow-lg shadow-indigo-600/20"
          >
            <Plus className="w-4 h-4" />
            <span>New Ticket</span>
          </button>
        </div>
      </header>

      {/* Main Content Layout */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left Side: Ticket List */}
        <section className={`flex-1 flex flex-col border-r border-slate-800 ${selectedTicket ? "hidden md:flex md:w-1/2 lg:w-5/12" : "w-full"}`}>
          {/* Filters Bar */}
          <div className="p-4 border-b border-slate-800 bg-slate-900/30 flex flex-wrap gap-2">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
              <input
                type="text"
                placeholder="Search subject..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500"
            >
              <option value="">All Statuses</option>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="pending">Pending</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>

            <select
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none focus:border-indigo-500"
            >
              <option value="">All Priorities</option>
              <option value="urgent">Urgent</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          {/* Error Banner */}
          {errorMessage && (
            <div className="m-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                <span>{errorMessage}</span>
              </div>
              <button onClick={() => setErrorMessage(null)} className="text-xs hover:underline">
                Dismiss
              </button>
            </div>
          )}

          {/* Ticket Items List */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
            {loadingTickets ? (
              <div className="p-8 text-center text-slate-500">
                <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
                <p className="text-sm">Loading tickets...</p>
              </div>
            ) : tickets.length === 0 ? (
              <div className="p-12 text-center text-slate-500">
                <Inbox className="w-10 h-10 mx-auto mb-3 opacity-40" />
                <p className="font-medium text-slate-300 mb-1">No tickets found</p>
                <p className="text-sm">Create a new ticket or adjust your active filters.</p>
              </div>
            ) : (
              tickets.map((ticket) => {
                const isSelected = selectedTicket?.id === ticket.id;
                return (
                  <button
                    key={ticket.id}
                    onClick={() => openTicketDetail(ticket)}
                    className={`w-full text-left p-4 hover:bg-slate-900/50 transition flex flex-col gap-1.5 ${
                      isSelected ? "bg-indigo-950/20 border-l-4 border-indigo-500" : ""
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-semibold text-indigo-400">
                        {ticket.ticket_reference}
                      </span>
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-medium ${
                            ticket.priority === "urgent"
                              ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                              : ticket.priority === "high"
                              ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {ticket.priority}
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-medium ${
                            ticket.status === "open"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : ticket.status === "in_progress"
                              ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                              : ticket.status === "resolved"
                              ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {ticket.status}
                        </span>
                      </div>
                    </div>

                    <h3 className="font-medium text-slate-200 line-clamp-1">{ticket.subject}</h3>

                    <div className="flex items-center justify-between text-xs text-slate-500 mt-1">
                      <span>Channel: {ticket.channel}</span>
                      <span>{new Date(ticket.created_at).toLocaleDateString()}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          <div className="p-3 border-t border-slate-800/80 bg-slate-900/40 text-xs text-slate-400 flex justify-between">
            <span>Showing {tickets.length} of {totalTickets} records</span>
            <span>RLS Active</span>
          </div>
        </section>

        {/* Right Side: Conversation / Detail View */}
        <section className={`flex-1 flex flex-col bg-slate-950 ${selectedTicket ? "flex" : "hidden md:flex"}`}>
          {selectedTicket ? (
            <div className="flex-1 flex flex-col h-full">
              {/* Ticket Detail Header */}
              <div className="p-5 border-b border-slate-800 bg-slate-900/40 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setSelectedTicket(null)}
                      className="md:hidden p-1.5 rounded-lg bg-slate-800 text-slate-300"
                    >
                      ←
                    </button>
                    <span className="font-mono text-sm font-bold text-indigo-400">
                      {selectedTicket.ticket_reference}
                    </span>
                    <span className="text-xs text-slate-500">v{selectedTicket.lock_version}</span>
                  </div>

                  {/* Status / Priority Controls */}
                  <div className="flex items-center gap-2">
                    <select
                      value={selectedTicket.status}
                      onChange={(e) => handleUpdateTicket(e.target.value as TicketStatus, undefined)}
                      className="bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded px-2.5 py-1"
                    >
                      <option value="open">Open</option>
                      <option value="in_progress">In Progress</option>
                      <option value="pending">Pending</option>
                      <option value="resolved">Resolved</option>
                      <option value="closed">Closed</option>
                    </select>

                    <select
                      value={selectedTicket.priority}
                      onChange={(e) => handleUpdateTicket(undefined, e.target.value as TicketPriority)}
                      className="bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded px-2.5 py-1"
                    >
                      <option value="urgent">Urgent</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                </div>

                <h2 className="text-lg font-bold text-slate-100">{selectedTicket.subject}</h2>
              </div>

              {/* Messages History */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {loadingMessages ? (
                  <div className="p-8 text-center text-slate-500">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
                    <span>Loading conversation history...</span>
                  </div>
                ) : messages.length === 0 ? (
                  <div className="p-8 text-center text-slate-500">
                    <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    <p className="text-sm">No messages in this thread yet.</p>
                  </div>
                ) : (
                  messages.map((msg) => {
                    const isOutbound = msg.direction === "outbound";
                    return (
                      <div
                        key={msg.id}
                        className={`flex flex-col max-w-2xl ${
                          isOutbound ? "ml-auto items-end" : "mr-auto items-start"
                        }`}
                      >
                        <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
                          <span className="font-medium text-slate-400">
                            {msg.sender_display_name || msg.author_type}
                          </span>
                          <span>•</span>
                          <span>{new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                        </div>
                        <div
                          className={`p-4 rounded-2xl text-sm leading-relaxed ${
                            isOutbound
                              ? "bg-indigo-600 text-white rounded-tr-none shadow-md shadow-indigo-600/10"
                              : "bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none"
                          }`}
                        >
                          <p className="whitespace-pre-wrap">{msg.body_text}</p>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Reply Input Box */}
              <form onSubmit={handleSendReply} className="p-4 border-t border-slate-800 bg-slate-900/40 flex gap-2">
                <input
                  type="text"
                  placeholder="Type an internal support message or reply..."
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
                <button
                  type="submit"
                  disabled={sendingReply || !replyText.trim() || conversations.length === 0}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium text-sm flex items-center gap-1.5 transition"
                >
                  {sendingReply ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  <span>Send</span>
                </button>
              </form>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-500">
              <MessageSquare className="w-12 h-12 mb-3 opacity-20" />
              <p className="font-medium text-slate-400">No ticket selected</p>
              <p className="text-sm">Select a ticket from the left panel to inspect details and conversation history.</p>
            </div>
          )}
        </section>
      </main>

      {/* New Ticket Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg p-6 shadow-2xl">
            <h2 className="text-lg font-bold text-slate-100 mb-4">Create Support Ticket</h2>
            <form onSubmit={handleCreateTicket} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Subject *</label>
                <input
                  type="text"
                  required
                  placeholder="Summary of the issue..."
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Priority</label>
                <select
                  value={newPriority}
                  onChange={(e) => setNewPriority(e.target.value as TicketPriority)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="urgent">Urgent</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Initial Description / Note</label>
                <textarea
                  rows={3}
                  placeholder="Detailed explanation of the support case..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm text-slate-300 font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingTicket || !newSubject.trim()}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm text-white font-medium flex items-center gap-2 transition shadow-lg shadow-indigo-600/20"
                >
                  {creatingTicket ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  <span>Create Ticket</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
