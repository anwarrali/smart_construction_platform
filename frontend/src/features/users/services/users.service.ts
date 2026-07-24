import api from "../../../services/api";
import type {
  UserFilters,
  UsersResponse,
  UserProfile,
  UpdateProfileRequest,
} from "../../../types/user";
import type { CreateUserRequest, CreateUserResponse, UpdateUserRequest } from "../../../types/auth";

export const usersService = {
  list: async (filters?: UserFilters): Promise<UsersResponse> => {
    return api.users.list(filters);
  },
  getById: async (id: string): Promise<UserProfile> => {
    return api.users.getById(id);
  },
  getProfile: async (): Promise<UserProfile> => {
    return api.users.getProfile();
  },
  updateProfile: async (data: UpdateProfileRequest): Promise<UserProfile> => {
    return api.users.updateProfile(data);
  },
  changePassword: async (
    currentPassword: string,
    newPassword: string,
  ): Promise<void> => {
    return api.users.changePassword(currentPassword, newPassword);
  },
  uploadAvatar: async (file: File): Promise<{ avatarUrl: string }> => {
    return api.users.uploadAvatar(file);
  },
  deactivate: async (id: string): Promise<void> => {
    return api.users.deactivate(id);
  },
  activate: async (id: string): Promise<void> => {
    return api.users.activate(id);
  },
  delete: async (id: string): Promise<void> => {
    return api.users.delete(id);
  },
  create: async (data: CreateUserRequest): Promise<CreateUserResponse> => {
    return api.users.create(data);
  },
  update: async (id: string, data: UpdateUserRequest): Promise<UserProfile> => {
    return api.users.update(id, data);
  },
  resetPassword: async (id: string): Promise<{ temporaryPassword: string; mustChangePassword: boolean }> => {
    return api.users.resetPassword(id);
  },
};
